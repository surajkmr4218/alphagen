from __future__ import annotations

import asyncio
import logging
from typing import Any

# Module-top imports (not lazy) so tests can monkeypatch app.api.runs.* directly.
from app.agents.graph import run_graph
from app.db import SessionLocal, session_scope
from app.execution.dal import ExecutionRepo
from app.ingestion.edgar import ensure_corpus
from app.models import User

log = logging.getLogger("runs")

# Global variable prevents Garbage Collector from acting on these tasks
_TASKS: set[asyncio.Task] = set()


def launch_run(graph: Any, decision_id: str, ticker: str, clerk_user_id: str) -> None:
    task = asyncio.create_task(_run_pipeline(graph, decision_id, ticker, clerk_user_id))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)

def _mark(decision_id: str, clerk_user_id: str, status: str, *, reason: str | None = None) -> None:
    with session_scope() as db:
        ExecutionRepo(db, clerk_user_id).mark_run_status(decision_id, status, reason=reason)


async def _run_pipeline(graph: Any, decision_id: str, ticker: str, clerk_user_id: str) -> None:
    """Drive one UI-submitted run to a terminal, DB-visible state — it must never just
    disappear or spin forever. The stub Decision row (human_decision='running') already
    exists; this flips it to 'pending' (parked at the approval gate), 'rejected'
    (system-resolved), or 'failed' (+reason). Owns its own sessions: the request session
    that created the stub row is long closed (same pattern as reconcile_tick)."""
    try:
        # Ingest first (sync EDGAR fetch + embeddings -> thread, not the event loop).
        await asyncio.to_thread(ensure_corpus, ticker)

        with SessionLocal() as s:
            user = s.query(User).filter_by(clerk_user_id=clerk_user_id).one()
        await run_graph(graph, ticker, user, decision_id=decision_id)

        # Parked at interrupt_before=["execute"] -> awaiting the human gate. Anything else
        # ran to END without an executable trade (guardrail hard-fail / abstain — the critic
        # is advisory and no longer ends a run).
        snap = await graph.aget_state({"configurable": {"thread_id": decision_id}})
        status = "pending" if snap.next == ("execute",) else "rejected"
        _mark(decision_id, clerk_user_id, status)
    except Exception as exc:  # noqa: BLE001 — every failure must land as a visible state
        log.warning("run %s (%s) failed: %s", decision_id, ticker, exc)
        _mark(decision_id, clerk_user_id, "failed", reason=f"{type(exc).__name__}: {exc}")


