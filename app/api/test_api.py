"""API tests for the dashboard-upgrade endpoints. No network, no live DB, no live orders:
brokers are fakes/stubs, repos are either in-memory fakes or the REAL ExecutionRepo against
sqlite (run-state verbs), and the app's lifespan (Postgres, GRAPH build) never runs because
TestClient is used without its context manager."""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.api.main as api_main
import app.api.runs as api_runs
import app.execution.quotes as quotes
from app.api.main import app, current_user, get_db, get_read_repo, get_repo
from app.execution.dal import ExecutionRepo
from app.models import Decision, Order, Outcome

client = TestClient(app)

OWNER = SimpleNamespace(clerk_user_id="owner-1", role="owner", robinhood_linked=True)
PUBLIC = SimpleNamespace(clerk_user_id="viewer-1", role="public", robinhood_linked=False)


@pytest.fixture(autouse=True)
def _clean_state():
    yield
    app.dependency_overrides.clear()
    quotes._CACHE.clear()
    api_main._ACCOUNT_LAST_GOOD = None
    api_main.GRAPH = None


def _use(user, repo=None):
    app.dependency_overrides[current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: None
    if repo is not None:
        app.dependency_overrides[get_repo] = lambda: repo
        app.dependency_overrides[get_read_repo] = lambda: repo


# --- fakes ------------------------------------------------------------------


class FakeGraph:
    def __init__(self, next_=()):
        self.next_ = next_

    async def aget_state(self, cfg):
        return SimpleNamespace(next=self.next_)


class FakeBroker:
    def __init__(self, quote=110.0, fail=False):
        self.quote = quote
        self.fail = fail
        self.quote_calls = 0

    async def get_quote(self, symbol):
        self.quote_calls += 1
        if self.fail:
            raise RuntimeError("quote unavailable")
        return self.quote

    async def portfolio(self):
        if self.fail:
            raise RuntimeError("broker down")
        return {"total_equity": 51.5, "cash": 20.0, "buying_power": 20.0}


def _decision(**over):
    row = SimpleNamespace(
        decision_id="d-1", ticker="AAPL", passed=True, human_decision="pending",
        created_at=datetime.now(UTC), hypothesis={"size_usd": 5.0}, guardrail={},
    )
    for k, v in over.items():
        setattr(row, k, v)
    return row


class FakeRepo:
    """In-memory stand-in exposing only the verbs the endpoints use."""

    def __init__(self, rows=None, running=None, pending=None):
        self.session = None
        self.rows = rows or []                # (decision, order, outcome) triples
        self.running = running                # active_run_for result
        self.pending = pending or []          # pending_decisions_for result
        self.created: list[tuple] = []
        self.marked: list[tuple] = []

    def active_run_for(self, ticker, *, stale_minutes=30):
        return self.running

    def pending_decisions_for(self, ticker):
        return self.pending

    def create_running_decision(self, decision_id, ticker, user_id):
        self.created.append((decision_id, ticker, user_id))

    def mark_run_status(self, decision_id, status, *, reason=None):
        self.marked.append((decision_id, status, reason))

    def get_decision(self, decision_id):
        for d, _, _ in self.rows:
            if d.decision_id == decision_id:
                return d
        return None

    def list_decisions_with_fills(self, limit=20):
        return self.rows


# --- sqlite harness for the REAL ExecutionRepo run-state verbs ----------------


@pytest.fixture()
def db_engine():
    # StaticPool: every session shares ONE in-memory sqlite connection, so code that opens
    # its own session (execution_node) sees the same data as the test's session.
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    for table in (Decision.__table__, Order.__table__, Outcome.__table__):
        table.create(engine)
    return engine


@pytest.fixture()
def db_session(db_engine):
    session = sessionmaker(bind=db_engine)()
    yield session
    session.close()


# --- POST /owner/hypotheses ---------------------------------------------------


@pytest.mark.parametrize("bad", ["aapl1", "TOOLONG", "", "BR K"])
def test_new_hypothesis_rejects_bad_ticker(bad):
    _use(OWNER, FakeRepo())
    assert client.post("/owner/hypotheses", json={"ticker": bad}).status_code == 422


def test_new_hypothesis_happy_path(monkeypatch):
    repo = FakeRepo()
    _use(OWNER, repo)
    api_main.GRAPH = FakeGraph()
    launched = []
    monkeypatch.setattr(api_main, "launch_run", lambda *a: launched.append(a))

    r = client.post("/owner/hypotheses", json={"ticker": "aapl"})
    assert r.status_code == 202
    body = r.json()
    assert body["ticker"] == "AAPL" and body["status"] == "running"
    assert repo.created == [(body["decision_id"], "AAPL", "owner-1")]
    assert launched and launched[0][1] == body["decision_id"]


def test_new_hypothesis_409_on_running(monkeypatch):
    running = _decision(decision_id="d-run", human_decision="running")
    _use(OWNER, FakeRepo(running=running))
    monkeypatch.setattr(api_main, "launch_run", lambda *a: pytest.fail("must not launch"))

    r = client.post("/owner/hypotheses", json={"ticker": "AAPL"})
    assert r.status_code == 409
    assert r.json()["detail"]["decision_id"] == "d-run"


def test_new_hypothesis_409_on_parked_pending(monkeypatch):
    pending = _decision(decision_id="d-parked")
    _use(OWNER, FakeRepo(pending=[pending]))
    api_main.GRAPH = FakeGraph(next_=("execute",))
    monkeypatch.setattr(api_main, "launch_run", lambda *a: pytest.fail("must not launch"))

    r = client.post("/owner/hypotheses", json={"ticker": "AAPL"})
    assert r.status_code == 409
    assert r.json()["detail"]["decision_id"] == "d-parked"


def test_new_hypothesis_allows_legacy_unparked_pending(monkeypatch):
    # Legacy critic-rejected rows stay 'pending' forever but are NOT parked at execute.
    repo = FakeRepo(pending=[_decision(decision_id="d-legacy")])
    _use(OWNER, repo)
    api_main.GRAPH = FakeGraph(next_=())
    monkeypatch.setattr(api_main, "launch_run", lambda *a: None)

    assert client.post("/owner/hypotheses", json={"ticker": "AAPL"}).status_code == 202
    assert repo.created


def test_stale_running_row_does_not_block(db_session, monkeypatch):
    # Real repo + sqlite: a 2h-old 'running' row is outside the staleness window.
    repo = ExecutionRepo(db_session)
    repo.create_running_decision("d-old", "AAPL", "owner-1")
    old = db_session.get(Decision, "d-old")
    old.created_at = datetime.now(UTC) - timedelta(hours=2)
    db_session.commit()

    assert repo.active_run_for("AAPL") is None
    repo.create_running_decision("d-new", "AAPL", "owner-1")
    assert repo.active_run_for("AAPL").decision_id == "d-new"


# --- background runner ---------------------------------------------------------


def _patch_runner(monkeypatch, repo, *, corpus_exc=None, graph_exc=None, parked=True):
    monkeypatch.setattr(api_runs, "ensure_corpus", lambda t: (_ for _ in ()).throw(corpus_exc)
                        if corpus_exc else None)

    class _S:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def query(self, model):
            return SimpleNamespace(filter_by=lambda **kw: SimpleNamespace(one=lambda: OWNER))

    monkeypatch.setattr(api_runs, "SessionLocal", _S)

    async def fake_run_graph(graph, ticker, user, *, decision_id=None, query=None):
        if graph_exc:
            raise graph_exc
        return {}

    monkeypatch.setattr(api_runs, "run_graph", fake_run_graph)
    monkeypatch.setattr(api_runs, "session_scope",
                        lambda uid: contextlib.nullcontext(None))
    monkeypatch.setattr(api_runs, "ExecutionRepo", lambda db, user_id=None: repo)
    return FakeGraph(next_=("execute",) if parked else ())


def test_run_pipeline_ingest_failure_marks_failed(monkeypatch):
    repo = FakeRepo()
    graph = _patch_runner(monkeypatch, repo, corpus_exc=ValueError("ZZZZZ has no SEC mapping"))
    asyncio.run(api_runs._run_pipeline(graph, "d-1", "ZZZZZ", "owner-1"))
    assert repo.marked == [("d-1", "failed", "ValueError: ZZZZZ has no SEC mapping")]


def test_run_pipeline_parked_marks_pending(monkeypatch):
    repo = FakeRepo()
    graph = _patch_runner(monkeypatch, repo, parked=True)
    asyncio.run(api_runs._run_pipeline(graph, "d-1", "AAPL", "owner-1"))
    assert repo.marked == [("d-1", "pending", None)]


def test_run_pipeline_end_marks_rejected(monkeypatch):
    repo = FakeRepo()
    graph = _patch_runner(monkeypatch, repo, parked=False)
    asyncio.run(api_runs._run_pipeline(graph, "d-1", "AAPL", "owner-1"))
    assert repo.marked == [("d-1", "rejected", None)]


def test_run_pipeline_graph_error_marks_failed(monkeypatch):
    repo = FakeRepo()
    graph = _patch_runner(monkeypatch, repo, graph_exc=RuntimeError("llm exploded"))
    asyncio.run(api_runs._run_pipeline(graph, "d-1", "AAPL", "owner-1"))
    assert repo.marked == [("d-1", "failed", "RuntimeError: llm exploded")]


def test_mark_run_status_stores_guardrail_reason(db_session):
    repo = ExecutionRepo(db_session)
    repo.create_running_decision("d-f", "AAPL", "owner-1")
    repo.mark_run_status("d-f", "failed", reason="UnknownTickerError: nope")

    d = db_session.get(Decision, "d-f")
    assert d.human_decision == "failed"
    assert d.guardrail["results"][0]["rule"] == "pipeline"
    assert d.guardrail["results"][0]["reason"] == "UnknownTickerError: nope"


# --- GET /owner/runs/{id} -------------------------------------------------------


def test_run_status_mapping():
    fresh = _decision(decision_id="d-r", human_decision="running")
    stale = _decision(decision_id="d-s", human_decision="running",
                      created_at=datetime.now(UTC) - timedelta(hours=2))
    failed = _decision(decision_id="d-f", human_decision="failed", guardrail={
        "passed": False,
        "results": [{"rule": "pipeline", "passed": False, "severity": "hard",
                     "reason": "boom"}],
    })
    parked = _decision(decision_id="d-p", human_decision="pending")
    done = _decision(decision_id="d-a", human_decision="approved")
    rows = [(d, None, None) for d in (fresh, stale, failed, parked, done)]
    _use(OWNER, FakeRepo(rows=rows))

    get = lambda i: client.get(f"/owner/runs/{i}").json()  # noqa: E731
    assert get("d-r")["status"] == "running"
    assert get("d-s") == {"decision_id": "d-s", "status": "failed",
                          "reason": "stale — worker restarted mid-run"}
    assert get("d-f")["reason"] == "boom"
    assert get("d-p")["status"] == "pending-approval"
    assert get("d-a") == {"decision_id": "d-a", "status": "complete",
                          "human_decision": "approved"}
    assert client.get("/owner/runs/nope").status_code == 404


# --- GET /account ----------------------------------------------------------------


def test_account_public_gets_demo_values():
    _use(PUBLIC)
    assert client.get("/account").json() == {
        "total_equity": 50.0, "cash": 25.0, "buying_power": 25.0, "stale": False,
    }


def test_account_owner_live_then_stale_fallback(monkeypatch):
    _use(OWNER)
    good = FakeBroker()
    monkeypatch.setattr(api_main, "_build_broker", lambda u, s, e: good)
    assert client.get("/account").json() == {
        "total_equity": 51.5, "cash": 20.0, "buying_power": 20.0, "stale": False,
    }

    monkeypatch.setattr(api_main, "_build_broker", lambda u, s, e: FakeBroker(fail=True))
    assert client.get("/account").json() == {
        "total_equity": 51.5, "cash": 20.0, "buying_power": 20.0, "stale": True,
    }


def test_account_owner_error_before_any_snapshot(monkeypatch):
    _use(OWNER)
    monkeypatch.setattr(api_main, "_build_broker", lambda u, s, e: FakeBroker(fail=True))
    assert client.get("/account").json() == {**api_main._DEMO_ACCOUNT, "stale": True}


# --- GET /decisions (P&L enrichment) ----------------------------------------------


def _filled_rows():
    order = SimpleNamespace(status="filled", qty=0.05)
    outcome = SimpleNamespace(fill_price=100.0)
    return [
        (_decision(decision_id="d-1", human_decision="approved"), order, outcome),
        (_decision(decision_id="d-2", human_decision="approved"), order, outcome),  # same ticker
        (_decision(decision_id="d-3", human_decision="rejected", hypothesis={}), None, None),
    ]


def test_decisions_pnl_math_and_single_quote_per_ticker(monkeypatch):
    _use(OWNER, FakeRepo(rows=_filled_rows()))
    broker = FakeBroker(quote=110.0)
    monkeypatch.setattr(api_main, "_build_broker", lambda u, s, e: broker)
    monkeypatch.setattr(api_main, "_load_user", lambda s, uid: OWNER)

    items = client.get("/decisions").json()
    filled = items[0]
    assert filled["size_usd"] == 5.0
    assert filled["order_status"] == "filled"
    assert filled["entry"] == 5.0                  # 100.0 * 0.05
    assert filled["current_price"] == 110.0
    assert filled["unrealized_pnl_pct"] == 10.0
    assert items[1]["unrealized_pnl_pct"] == 10.0
    assert broker.quote_calls == 1                 # TTL cache: one call per DISTINCT ticker

    bare = items[2]
    assert bare["size_usd"] is None and bare["order_status"] is None
    assert bare["entry"] is None and bare["unrealized_pnl_pct"] is None


def test_decisions_quote_failure_yields_null_pnl(monkeypatch):
    _use(OWNER, FakeRepo(rows=_filled_rows()))
    monkeypatch.setattr(api_main, "_build_broker", lambda u, s, e: FakeBroker(fail=True))
    monkeypatch.setattr(api_main, "_load_user", lambda s, uid: OWNER)

    r = client.get("/decisions")
    assert r.status_code == 200
    assert all(i["unrealized_pnl_pct"] is None for i in r.json())


def test_decisions_public_uses_stub_quotes():
    rows = [(_decision(human_decision="approved"),
             SimpleNamespace(status="filled", qty=0.05),
             SimpleNamespace(fill_price=80.0))]
    _use(PUBLIC, FakeRepo(rows=rows))

    item = client.get("/decisions").json()[0]
    assert item["current_price"] == 100.0          # StubBroker static quote
    assert item["unrealized_pnl_pct"] == 25.0


# --- write_decision merge must not clobber the stub's run state --------------------


def test_write_decision_merge_preserves_running_state(db_session):
    from app.agents.logging import write_decision

    ExecutionRepo(db_session).create_running_decision("d-m", "AAPL", "owner-1")
    write_decision(db_session, {
        "decision_id": "d-m", "ticker": "AAPL",
        "evidence": {"passages": []}, "hypothesis": {"size_usd": 5.0},
        "critic_verdict": {"verdict": "reject"}, "guardrail": {},
    }, user_id="owner-1")

    d = db_session.get(Decision, "d-m")
    assert d.human_decision == "running"           # survived the merge
    assert d.hypothesis == {"size_usd": 5.0}       # trail fields were written


# --- execution check-twice: reason + guardrail must land in the DB -----------------


_EVIDENCE = {"passages": [{"accession": "0000320193-25-000001", "section": "item 1a",
                           "text": "Risk factor language changed materially."}]}


def _exec_state(decision_id: str) -> dict:
    return {
        "clerk_user_id": "owner-1", "execution_enabled": True,
        "decision_id": decision_id, "ticker": "AAPL", "evidence": _EVIDENCE,
        "hypothesis": {
            "ticker": "AAPL", "direction": "long", "order_type": "market",
            "limit_price": None, "size_usd": 3.0, "confidence": 0.75,
            "rationale": "test",
            "citations": [{"accession": "0000320193-25-000001", "section": "item 1a"}],
        },
    }


def _seed_approved_decision(db_session, decision_id: str) -> None:
    # What log_node + approval leave behind: an all-PASS first-pass guardrail + pending Order.
    db_session.add(Decision(
        decision_id=decision_id, ticker="AAPL", user_id="owner-1",
        human_decision="approved", passed=True, created_at=datetime.now(UTC),
        guardrail={"passed": True, "results": []},
    ))
    db_session.add(Order(
        decision_id=decision_id, user_id="owner-1", symbol="AAPL", side="buy",
        order_type="market", size_usd=3.0, status="pending", created_at=datetime.now(UTC),
    ))
    db_session.commit()


def _run_execution_node(db_engine, monkeypatch, broker, decision_id):
    import app.execution.execute as execute

    monkeypatch.setattr(execute, "SessionLocal", sessionmaker(bind=db_engine))
    monkeypatch.setattr(execute, "_load_user", lambda s, uid: OWNER)
    monkeypatch.setattr(execute, "_build_broker", lambda u, s, e: broker)
    return asyncio.run(execute.execution_node(_exec_state(decision_id)))


def test_check_twice_rejection_persists_reason_and_guardrail(db_engine, db_session, monkeypatch):
    from app.execution.robinhood import StubBroker

    class ClosedMarketStub(StubBroker):
        def market_open(self, now=None):
            return False

    _seed_approved_decision(db_session, "d-exec")
    result = _run_execution_node(db_engine, monkeypatch, ClosedMarketStub(), "d-exec")
    assert result["order"]["status"] == "rejected"
    assert "market CLOSED" in result["order"]["reason"]

    order = db_session.get(Order, "d-exec")
    db_session.refresh(order)
    assert order.status == "rejected"
    assert order.reason == "check_twice: market CLOSED at execution"

    dec = db_session.get(Decision, "d-exec")
    db_session.refresh(dec)
    failed = {r["rule"] for r in dec.guardrail["results"] if not r["passed"]}
    assert failed == {"market_hours"}          # the trail now shows WHY, not stale all-PASS
    assert dec.passed is False


def test_check_twice_pass_places_stub_order_and_updates_guardrail(
    db_engine, db_session, monkeypatch
):
    from app.execution.robinhood import StubBroker

    _seed_approved_decision(db_session, "d-ok")
    result = _run_execution_node(db_engine, monkeypatch, StubBroker(), "d-ok")
    assert result["order"]["status"] == "filled"          # StubBroker fake fill — no live order
    assert result["order"]["broker_order_id"].startswith("STUB-")

    dec = db_session.get(Decision, "d-ok")
    db_session.refresh(dec)
    rules = {r["rule"]: r["passed"] for r in dec.guardrail["results"]}
    assert rules["market_hours"] is True and rules["price_sanity"] is True
    assert dec.passed is True


# --- graph shape: the critic is advisory, guardrails still gate ---------------------


def test_critic_does_not_gate_the_graph():
    from app.agents.graph import _after_log, build_graph

    edges = {(e.source, e.target) for e in build_graph(None).get_graph().edges}
    assert ("critic", "guardrail") in edges     # every hypothesis reaches the guardrail
    assert ("critic", "log") not in edges       # the critic lost its shortcut veto

    # Deterministic gate unchanged: only guardrail-passed owner runs reach execute.
    assert _after_log({"guardrail": {"passed": True}, "execution_enabled": True}) == "execute"
    assert _after_log({"guardrail": {"passed": False}, "execution_enabled": True}) == "END"
    assert _after_log({"guardrail": {"passed": True}, "execution_enabled": False}) == "END"


# --- real-repo fills join -----------------------------------------------------------


def test_list_decisions_with_fills_joins_and_dedupes(db_session):
    repo = ExecutionRepo(db_session)
    db_session.add(Decision(decision_id="d-x", ticker="AAPL", user_id="u",
                            human_decision="approved", passed=True,
                            created_at=datetime.now(UTC)))
    db_session.add(Order(decision_id="d-x", user_id="u", symbol="AAPL", side="buy",
                         order_type="market", size_usd=5.0, qty=0.05, status="filled",
                         created_at=datetime.now(UTC)))
    # Two Outcome rows for one decision (nothing enforces uniqueness) -> must dedupe.
    db_session.add(Outcome(decision_id="d-x", user_id="u", fill_price=100.0))
    db_session.add(Outcome(decision_id="d-x", user_id="u", fill_price=101.0))
    db_session.commit()

    rows = repo.list_decisions_with_fills()
    assert len(rows) == 1
    dec, order, outcome = rows[0]
    assert dec.decision_id == "d-x" and order.status == "filled"
    assert outcome.fill_price in (100.0, 101.0)


# --- tenant scoping: repo reads must filter by user_id (defense-in-depth vs RLS) ----
# sqlite has no RLS, so these tests prove the PYTHON layer alone keeps tenants apart.


def _seed_two_tenants(db_session):
    for uid, did, ret in (("owner-1", "d-own", 0.05), ("intruder", "d-other", 0.01)):
        db_session.add(Decision(decision_id=did, ticker="AAPL", user_id=uid,
                                human_decision="approved", passed=True,
                                created_at=datetime.now(UTC)))
        db_session.add(Order(decision_id=did, user_id=uid, symbol="AAPL", side="buy",
                             order_type="market", size_usd=5.0, qty=0.05, status="filled",
                             created_at=datetime.now(UTC)))
        db_session.add(Outcome(decision_id=did, user_id=uid, fill_price=100.0,
                               forward_return=ret, spy_return=0.0))
    db_session.commit()


def test_repo_reads_are_tenant_scoped(db_session):
    _seed_two_tenants(db_session)
    repo = ExecutionRepo(db_session, "owner-1")

    assert [d.decision_id for d in repo.list_decisions()] == ["d-own"]
    assert [d.decision_id for d, _, _ in repo.list_decisions_with_fills()] == ["d-own"]
    assert repo.get_decision("d-own") is not None
    assert repo.get_decision("d-other") is None          # other tenant's trail -> invisible
    assert repo.get_order("d-other") is None
    assert repo.eval_summary()["n_resolved"] == 1        # performance panel: own rows only


def test_repo_without_tenant_stays_unscoped_for_system_paths(db_session):
    # Cron/execution sessions pass no tenant — they must keep seeing everything.
    _seed_two_tenants(db_session)
    repo = ExecutionRepo(db_session)
    assert len(repo.list_decisions()) == 2
    assert repo.eval_summary()["n_resolved"] == 2


# --- RobinhoodBroker.portfolio: field names pinned to the observed payload ----------
# Verbatim shape from the Session-0 preflight raw dump (2026-07-17): money values are
# strings, buying_power is nested one level. No guessing, no get_accounts fallback.

_PORTFOLIO_PAYLOAD = {
    "data": {
        "total_value": "50.1908924",
        "equity_value": "5.2008924",
        "options_value": "0",
        "cash": "44.99",
        "pending_deposits": "0",
        "currency": "USD",
        "buying_power": {
            "buying_power": "44.9900",
            "unleveraged_buying_power": "44.9900",
            "display_currency": "USD",
        },
    }
}


def _mcp_broker(payload):
    """Real RobinhoodBroker with _call faked at the MCP boundary (content-block shape)."""
    from app.execution.robinhood import RobinhoodBroker

    broker = RobinhoodBroker("000000000", auth=None)
    calls: list[str] = []

    async def fake_call(name, **kwargs):
        calls.append(name)
        return [{"type": "text", "text": json.dumps(payload)}]

    broker._call = fake_call
    return broker, calls


def test_portfolio_maps_pinned_payload_fields():
    broker, calls = _mcp_broker(_PORTFOLIO_PAYLOAD)
    snap = asyncio.run(broker.portfolio())
    assert snap == {"total_equity": 50.1908924, "cash": 44.99, "buying_power": 44.99}
    assert calls == ["get_portfolio"]


def test_portfolio_missing_field_is_none_without_fallback_calls():
    # equity fields absent -> None (dashboard renders a dash); pinned names mean there is
    # no second get_accounts guessing call, ever.
    payload = {"data": {"cash": "44.99", "buying_power": {"buying_power": "44.9900"}}}
    broker, calls = _mcp_broker(payload)
    snap = asyncio.run(broker.portfolio())
    assert snap == {"total_equity": None, "cash": 44.99, "buying_power": 44.99}
    assert calls == ["get_portfolio"]
