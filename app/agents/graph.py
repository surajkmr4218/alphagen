from __future__ import annotations

import uuid

from app.agents.state import TradeState
from app.models import User


def _after_log(state: TradeState) -> str:
    passed = (state.get("guardrail") or {}).get("passed", False)
    # The tier gate: only the owner (execution_enabled=True) may reach execute, and only
    # once the guardrails passed. Rejected runs have no guardrail -> passed False -> END.
    if passed and state.get("execution_enabled"):
        return "execute"
    return "END"


def build_graph(checkpointer):
    """Compile the trade graph ONCE against a durable checkpointer.

    No broker/db/cfg are injected here anymore: the execute node resolves its own resources at
    run time (see execution_node), which is what lets a resumed run work on a live session. The
    caller passes the process-wide AsyncPostgresSaver so paused threads survive across requests
    and process restarts (checkpoint state lives in Postgres, not in memory).
    """
    from langgraph.graph import END, START, StateGraph

    from app.agents.nodes import (
        critic_node,
        guardrail_node,
        hypothesis_node,
        log_node,
        research_node,
    )
    from app.execution.execute import execution_node

    g = StateGraph(TradeState)
    g.add_node("research", research_node)
    g.add_node("hypothesis", hypothesis_node)
    g.add_node("critic", critic_node)
    g.add_node("guardrail", guardrail_node)
    g.add_node("log", log_node)                # writes the Decision record for EVERY run
    g.add_node("execute", execution_node)

    g.add_edge(START, "research")
    g.add_edge("research", "hypothesis")
    g.add_edge("hypothesis", "critic")
    # The critic is ADVISORY: its verdict is recorded and shown at the approval gate, but it
    # never ends the run — the owner decides. Deterministic guardrails (including the hard
    # citations rule) still gate execution via _after_log. 
    g.add_edge("critic", "guardrail")
    g.add_edge("guardrail", "log")             # every run logs after the guardrail result
    g.add_conditional_edges("log", _after_log, {"execute": "execute", "END": END})
    g.add_edge("execute", END)

    # interrupt_before=["execute"] is the human-approval pause — the graph stops BEFORE
    # execute and waits for graph.ainvoke(None, config=...) after the owner approves. The
    # durable checkpointer persists state per thread_id so that resume works across requests.
    return g.compile(checkpointer=checkpointer, interrupt_before=["execute"])


async def run_graph(
    graph,
    ticker: str,
    user: User,
    *,
    query: str | None = None,
    decision_id: str | None = None,
) -> dict:
    """Assemble the initial TradeState and run the SINGLETON graph to its first stop.

    `graph` is the process-wide compiled singleton (built once in the FastAPI lifespan with the
    durable AsyncPostgresSaver) — we don't compile per call, and no request-scoped broker/
    session is injected because the execute node resolves its own. `execution_enabled` is still
    *derived* from role (never set by hand): public tier ends at END; owner tier pauses at
    interrupt_before=["execute"] for the approval gate. Async because the saver is async.
    """
    from app.models import execution_enabled_for

    decision_id = decision_id or str(uuid.uuid4())
    state: TradeState = {
        "clerk_user_id": user.clerk_user_id,  
        "ticker": ticker,
        "execution_enabled": execution_enabled_for(user),
        "decision_id": decision_id,
    }
    if query is not None:
        state["query"] = query

    cfg = {"configurable": {"thread_id": decision_id}}
    return await graph.ainvoke(state, config=cfg)
