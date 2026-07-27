from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import httpx
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from jose import jwt
from jose.exceptions import JWTError
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.agents.graph import build_graph
from app.api.runs import launch_run
from app.config import settings
from app.db import session_scope
from app.execution.dal import ExecutionRepo
from app.execution.execute import _build_broker, _load_user
from app.execution.quotes import cached_quote
from app.execution.reconcile import start_scheduler
from app.execution.robinhood import StubBroker
from app.models import User, execution_enabled_for
from app.security import link_robinhood

# Specify a GLOBAL graph variable so it holds the checkpointer and can resume properly
GRAPH = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global GRAPH
    # The saver speaks raw psycopg so it needs a libpq URL, not the SQLAlchemy '+psycopg' form.
    conninfo = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    async with AsyncPostgresSaver.from_conn_string(conninfo) as checkpointer:
        await checkpointer.setup()           # the saver's OWN tables (managed by LangGraph, independent of Alembic)
        scheduler = start_scheduler()        # reconcile cron; each tick owns its session/broker
        GRAPH = build_graph(checkpointer)    # singleton; build_graph takes only the checkpointer
        yield
        scheduler.shutdown(wait=False)

app = FastAPI(title="Alphagen", lifespan=lifespan)

# Specifies the type of requests that are allowed
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.allowed_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@lru_cache(maxsize=1)
def _jwks() -> dict:
    resp = httpx.get(settings.clerk_jwks_url, timeout=10.0)
    resp.raise_for_status()
    return resp.json()


def _verify_clerk_jwt(token: str) -> str:
    try:
        claims = jwt.decode(token, _jwks(), algorithms=["RS256"], options={"verify_aud": False})
    except JWTError as e:
        raise HTTPException(status_code=401, detail="invalid token") from e
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="token missing sub")
    return sub


def current_user_id(authorization: str = Header(default="")) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    return _verify_clerk_jwt(authorization.removeprefix("Bearer "))

def get_db() -> Iterator[Session]:
    with session_scope() as db:
        yield db

def get_repo(
    db: Session = Depends(get_db), clerk_user_id: str = Depends(current_user_id)
) -> ExecutionRepo:
    # The owner endpoints talk to the DB through the repo verbs, not raw ORM.  
    return ExecutionRepo(db, clerk_user_id)

def current_user(
    clerk_user_id: str = Depends(current_user_id), db: Session = Depends(get_db)
) -> User:
    user = db.query(User).filter_by(clerk_user_id=clerk_user_id).one_or_none()
    if user is None:  # first sign-in -> least-privilege default
        user = User(clerk_user_id=clerk_user_id, role="public")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

def get_read_repo(user: User = Depends(current_user)) -> Iterator[ExecutionRepo]:
    # Dashboard reads: the owner sees their own tenant. Everyone else (public/recruiter)
    # sees the seeded demo tenant.  
    tenant = user.clerk_user_id if user.role == "owner" else settings.demo_user_id
    with session_scope() as db:
        yield ExecutionRepo(db, tenant)


def require_owner(user: User = Depends(current_user)) -> User:  
    # The user row already carries the role — no DB round-trip needed for the gate.
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="owner only")
    return user

@app.get("/me")
def me(user: User = Depends(current_user)):
    return {
        "clerk_user_id": user.clerk_user_id,
        "role": user.role,
        "execution_enabled": execution_enabled_for(user),
        "robinhood_linked": user.robinhood_linked,
    }

@app.get("/onboarding/status")
def onboarding_status(user: User = Depends(current_user)) -> dict:
    return {"robinhood_linked": user.robinhood_linked}


class LinkPayload(BaseModel):
    access_token: str
    refresh_token: str | None = None


@app.post("/onboarding/link-robinhood")
def link_rh(
    payload: LinkPayload, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    link_robinhood(db, user, payload.access_token, payload.refresh_token)
    return {"robinhood_linked": True}  # do NOT echo the token back

router = APIRouter(prefix="/owner", tags=["execution"])


@router.get("/queue")
async def approval_queue(
    user: User = Depends(require_owner), repo: ExecutionRepo = Depends(get_repo)
):
    """Decisions paused at interrupt_before=['execute']."""
    out = []
    for d in repo.decisions_pending(user):               # human_decision == 'pending'
        # aget_state (not get_state): the checkpointer is async (AsyncPostgresSaver).
        snap = await GRAPH.aget_state({"configurable": {"thread_id": d.decision_id}})
        if snap.next == ("execute",):       # paused exactly at interrupt_before=["execute"]
            out.append({
                "decision_id": d.decision_id,
                "ticker": d.ticker,
                "hypothesis": snap.values["hypothesis"],
                "critic_verdict": snap.values.get("critic_verdict"),
                "guardrail": snap.values.get("guardrail"),
            })
    return out


@router.post("/approve/{decision_id}")
async def approve(
    decision_id: str,
    user: User = Depends(require_owner),
    repo: ExecutionRepo = Depends(get_repo),
):
    repo.set_human_decision(decision_id, "approved", user)
    cfg = {"configurable": {"thread_id": decision_id}}
    final = await GRAPH.ainvoke(None, config=cfg)        # resumes -> runs the async execute node
    return {"decision_id": decision_id, "order": final.get("order")}


@router.post("/reject/{decision_id}")
def reject(
    decision_id: str,
    user: User = Depends(require_owner),
    repo: ExecutionRepo = Depends(get_repo),
):
    repo.set_human_decision(decision_id, "rejected", user)
    # Do NOT resume. The graph stays parked; no broker call ever happens.
    return {"decision_id": decision_id, "status": "rejected"}


class NewHypothesis(BaseModel):
    ticker: str

    @field_validator("ticker")
    @classmethod
    def _valid_ticker(cls, v: str) -> str:
        v = v.strip().upper()
        if not re.fullmatch(r"[A-Z]{1,5}", v):
            raise ValueError("ticker must be 1-5 letters")
        return v


@router.post("/hypotheses", status_code=202)
async def create_hypothesis(
    payload: NewHypothesis,
    user: User = Depends(require_owner),
    repo: ExecutionRepo = Depends(get_repo),
):
    """Kick off one pipeline run for a ticker; the graph itself still pauses at the
    interrupt_before=["execute"] human gate. ONE ACTIVE RUN PER TICKER: an in-flight run
    or a decision parked at the approval gate blocks with a 409 carrying its decision_id
    (the UI jumps to that trail). Resolved runs (approved/rejected/failed) don't block."""
    ticker = payload.ticker
    blocker = repo.active_run_for(ticker)
    if blocker is None:
        for d in repo.pending_decisions_for(ticker):
            # Same parked-at-execute semantics as /owner/queue: legacy critic-rejected rows
            # sit at 'pending' without a parked thread and must not block resubmission.
            snap = await GRAPH.aget_state({"configurable": {"thread_id": d.decision_id}})
            if snap.next == ("execute",):
                blocker = d
                break
    if blocker is not None:
        raise HTTPException(status_code=409, detail={
            "decision_id": blocker.decision_id,
            "ticker": ticker,
            "message": "a run for this ticker is already in progress or awaiting approval",
        })

    decision_id = str(uuid.uuid4())
    repo.create_running_decision(decision_id, ticker, user.clerk_user_id)
    launch_run(GRAPH, decision_id, ticker, user.clerk_user_id)
    return {"decision_id": decision_id, "ticker": ticker, "status": "running"}


# active_run_for treats older 'running' rows as dead (worker restarted mid-run);
# report the same staleness here so the UI's poll terminates instead of spinning.
_RUN_STALE_MINUTES = 30


@router.get("/runs/{decision_id}")
def run_status(
    decision_id: str,
    user: User = Depends(require_owner),
    repo: ExecutionRepo = Depends(get_repo),
):
    d = repo.get_decision(decision_id)
    if d is None:
        raise HTTPException(status_code=404, detail="run not found")
    if d.human_decision == "running":
        created = d.created_at if d.created_at.tzinfo else d.created_at.replace(tzinfo=UTC)
        if datetime.now(UTC) - created < timedelta(minutes=_RUN_STALE_MINUTES):
            return {"decision_id": decision_id, "status": "running"}
        return {"decision_id": decision_id, "status": "failed",
                "reason": "stale"}
    if d.human_decision == "failed":
        results = (d.guardrail or {}).get("results") or [{}]
        return {"decision_id": decision_id, "status": "failed",
                "reason": results[0].get("reason")}
    if d.human_decision == "pending":
        return {"decision_id": decision_id, "status": "pending-approval"}
    return {"decision_id": decision_id, "status": "complete", "human_decision": d.human_decision}


"""
Dashboard read endpoints — owner sees own tenant, public sees demo.
"""

# Last snapshot that came back from the live broker. Served (marked stale) when the broker
# blips so the account bar never 500s; static demo values until the first good read.
_ACCOUNT_LAST_GOOD: dict | None = None
_DEMO_ACCOUNT = {"total_equity": 50.0, "cash": 25.0, "buying_power": 25.0}


@app.get("/account")
async def account(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Balance bar snapshot. Owner: live broker; public: static demo values. Never 500s."""
    global _ACCOUNT_LAST_GOOD
    if user.role != "owner":
        return {**_DEMO_ACCOUNT, "stale": False}
    try:
        # `user` is attached to this same `db` session, so DbTokenStorage refreshes land.
        snap = await _build_broker(user, db, True).portfolio()
        _ACCOUNT_LAST_GOOD = snap
        return {**snap, "stale": False}
    except Exception:  # noqa: BLE001 — a broker blip must never break the 30s poll
        return {**(_ACCOUNT_LAST_GOOD or _DEMO_ACCOUNT), "stale": True}


@app.get("/decisions")
async def list_decisions(
    user: User = Depends(current_user), repo: ExecutionRepo = Depends(get_read_repo)
):
    live = user.role == "owner"
    if live:
        # current_user loaded `user` on the get_db session; the broker's token storage
        # commits on the session it's handed, so reload on the repo's session.
        broker = _build_broker(_load_user(repo.session, user.clerk_user_id), repo.session, True)
    else:
        broker = StubBroker()

    out = []
    for d, order, outcome in repo.list_decisions_with_fills():
        item = {
            "decision_id": d.decision_id,
            "ticker": d.ticker,
            "passed": d.passed,
            "human_decision": d.human_decision,
            "created_at": d.created_at,
            "size_usd": (d.hypothesis or {}).get("size_usd"),  # old rows may lack it
            "order_status": order.status if order else None,
            "entry": None,
            "current_price": None,
            "unrealized_pnl_pct": None,
        }
        filled = (
            order is not None and order.status == "filled"
            and outcome is not None and outcome.fill_price and order.qty
        )
        if filled:
            # One get_quote per DISTINCT ticker per ~30s (TTL cache); None on failure —
            # the P&L fields go null, the endpoint never fails on a quote blip.
            price = await cached_quote(broker, d.ticker, live=live)
            if price is not None:
                item["entry"] = round(outcome.fill_price * order.qty, 2)
                item["current_price"] = price
                item["unrealized_pnl_pct"] = round(
                    (price - outcome.fill_price) / outcome.fill_price * 100, 1
                )
        out.append(item)
    return out


@app.get("/decisions/{decision_id}/trail")
def reasoning_trail(decision_id: str, repo: ExecutionRepo = Depends(get_read_repo)):
    d = repo.get_decision(decision_id)                    
    if d is None:                                        
        raise HTTPException(status_code=404, detail="decision not found")
    ev = d.evidence or {}                                  
    # build_diff_bundle annotates diffs per-passage (passages[].diff). Surface the first
    # (highest-ranked) annotated passage; null only when nothing changed YoY or there is
    # no prior same-form filing to diff against.
    p = next((p for p in ev.get("passages") or [] if p.get("diff")), None)
    diff = {"section": p.get("section"), **p["diff"]} if p is not None else None
    return {
        "ticker": d.ticker,
        "triggering_diff": diff,                   # {section, added, removed, semantic_drift}
        "cited_passages": ev.get("passages"),      # [{accession, section, text}]
        "signals": ev.get("signals"),              # insider/scores/news/consensus
        "hypothesis": d.hypothesis,                # direction, size_usd, confidence, rationale
        "critic_verdict": d.critic_verdict,        # accept/reject, reasons, unsupported_citations
        "guardrail": d.guardrail,                  # {passed, results:[{rule,...,reason}]}
        "order": repo.get_order(decision_id),      # status, qty, broker_order_id (or null)
    }


@app.get("/eval/summary")
def eval_summary(repo: ExecutionRepo = Depends(get_read_repo)):
    return repo.eval_summary()


# Mount the owner router — without this the /owner/* routes are never served (404).
app.include_router(router)