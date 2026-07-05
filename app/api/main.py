from __future__ import annotations

from collections.abc import Iterator
from contextlib import asynccontextmanager
from functools import lru_cache

import httpx
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from jose import jwt
from jose.exceptions import JWTError
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.graph import build_graph
from app.config import settings
from app.db import session_scope
from app.execution.dal import ExecutionRepo
from app.execution.reconcile import start_scheduler
from app.models import User, execution_enabled_for
from app.security import link_robinhood

GRAPH = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global GRAPH
    async with AsyncPostgresSaver.from_conn_string(settings.database_url) as checkpointer:
        await checkpointer.setup()           # the saver's OWN tables (independent of Alembic)
        await start_scheduler()
        GRAPH = build_graph(checkpointer)    # singleton; build_graph takes only the checkpointer
        yield

app = FastAPI(title="Alphagen", lifespan=lifespan)

# Browser calls come from the Vite dev origin; without this the preflight fails
# and every fetch from the SPA is blocked. curl bypasses CORS, so test in-browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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

def get_db(clerk_user_id: str = Depends(current_user_id)) -> Iterator[Session]:
    # session_scope sets the RLS GUC (app.user_id) to the same clerk_user_id that
    # write_decision stamps into the user_id column — one tenant key, set on every session.
    with session_scope(clerk_user_id) as db:
        yield db

def get_repo(db: Session = Depends(get_db)) -> ExecutionRepo:
    # The owner endpoints talk to the DB through the repo verbs, not raw ORM — and they
    # inherit the RLS-scoped session get_db already opened.
    return ExecutionRepo(db)

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
    # Dashboard reads: the owner sees their own tenant; everyone else (public/recruiter)
    # sees the seeded demo tenant. The tenant key goes into the RLS GUC, so the DB —
    # not endpoint code — enforces the scoping.
    tenant = user.clerk_user_id if user.role == "owner" else settings.demo_user_id
    with session_scope(tenant) as db:
        yield ExecutionRepo(db)


def require_owner(user: User = Depends(current_user)) -> User:   # current_user from Week 6
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
    reason: str = "",
    user: User = Depends(require_owner),
    repo: ExecutionRepo = Depends(get_repo),
):
    repo.set_human_decision(decision_id, "rejected", user, reason=reason)
    # Do NOT resume. The graph stays parked; no broker call ever happens.
    return {"decision_id": decision_id, "status": "rejected"}

# --- dashboard read endpoints — owner sees own tenant, public sees demo ---

@app.get("/decisions")
def list_decisions(repo: ExecutionRepo = Depends(get_read_repo)):
    return [
        {
            "decision_id": d.decision_id,
            "ticker": d.ticker,
            "passed": d.passed,
            "human_decision": d.human_decision,
            "created_at": d.created_at,
        }
        for d in repo.list_decisions()
    ]


@app.get("/decisions/{decision_id}/trail")
def reasoning_trail(decision_id: str, repo: ExecutionRepo = Depends(get_read_repo)):
    d = repo.get_decision(decision_id)                    # RLS scopes by app.user_id
    if d is None:                                         # missing OR another tenant's — same 404
        raise HTTPException(status_code=404, detail="decision not found")
    ev = d.evidence or {}                                 # pre-migration rows have no evidence
    return {
        "ticker": d.ticker,
        "triggering_diff": ev.get("diff"),         # {section, added, removed, semantic_drift}
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