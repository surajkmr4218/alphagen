from __future__ import annotations

import uuid
from functools import partial
from typing import Any

from app.agents.state import TradeState
from app.execution.dal import ExecutionRepo
from app.models import User


def _after_critic(state: TradeState) -> str:
    # Accept -> run guardrails; reject -> straight to logging (still recorded). Either way
    # the run reaches log_node, so every decision lands in the dashboard reasoning trail.
    v = (state.get("critic_verdict") or {}).get("verdict")
    return "guardrail" if v == "accept" else "log"


def _after_log(state: TradeState) -> str:
    passed = (state.get("guardrail") or {}).get("passed", False)
    # The tier gate: only the owner (execution_enabled=True) may reach execute, and only
    # once the guardrails passed. Rejected runs have no guardrail -> passed False -> END.
    if passed and state.get("execution_enabled"):
        return "execute"
    return "END"


def build_graph(broker: Any, db: ExecutionRepo, cfg: Any):
    """Compile the trade graph with the execution dependencies bound (Week 7).

    `broker`/`db`/`cfg` are injected into the execute node via partial — the DI seam from
    Week 4. `broker` is a RobinhoodBroker (owner) or StubBroker (paper); `db` is the request
    DB handle; `cfg` is guardrail_cfg() for the check-twice re-validation.
    """
    from langgraph.checkpoint.memory import MemorySaver
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
    g.add_node("execute", partial(execution_node, broker=broker, db=db, cfg=cfg))

    g.add_edge(START, "research")
    g.add_edge("research", "hypothesis")
    g.add_edge("hypothesis", "critic")
    g.add_conditional_edges("critic", _after_critic, {"guardrail": "guardrail", "log": "log"})
    g.add_edge("guardrail", "log")             # accept path logs after the guardrail result
    g.add_conditional_edges("log", _after_log, {"execute": "execute", "END": END})
    g.add_edge("execute", END)

    # MemorySaver persists state per thread_id so a paused run can be resumed (Week 7).
    # interrupt_before=["execute"] is the human-approval pause — the graph stops BEFORE
    # execute and waits for graph.invoke(None, config=...) after the owner approves.
    return g.compile(checkpointer=MemorySaver(), interrupt_before=["execute"])


def _build_broker(user: User, session: Any, execution_enabled: bool) -> Any:
    """Owner -> live RobinhoodBroker authed via the encrypted DB token; else paper StubBroker.

    Same DI seam as Week 4: the graph never knows which broker it got. Takes the raw Session
    because DbTokenStorage commits the user row directly.
    """
    from app.config import settings
    from app.execution.auth import robinhood_provider
    from app.execution.robinhood import RobinhoodBroker, StubBroker
    from app.security import DbTokenStorage

    if not execution_enabled:
        return StubBroker()
    storage = DbTokenStorage(session, user)  # OAuth token round-trips through the users row
    return RobinhoodBroker(settings.robinhood_account_number, auth=robinhood_provider(storage))


def run_graph(
    ticker: str,
    user: User,
    session: Any,
    *,
    query: str | None = None,
    decision_id: str | None = None,
) -> dict:
    """Assemble the initial TradeState for `user` and run the graph to its first stop.

    The Week-4 contract is frozen — `execution_enabled` is *derived* from the user's role
    via execution_enabled_for, never set by hand. Public tier ends at END; owner tier pauses
    at interrupt_before=["execute"] for the Week-7 approval gate. `session` is the request DB
    Session: the broker's token storage commits on it directly, while the execute node writes
    through an ExecutionRepo wrapping the same Session.
    """
    from app.config import guardrail_cfg
    from app.models import execution_enabled_for

    decision_id = decision_id or str(uuid.uuid4())
    execution_enabled = execution_enabled_for(user)
    state: TradeState = {
        "clerk_user_id": user.clerk_user_id,  # the one tenant key 
        "ticker": ticker,
        "execution_enabled": execution_enabled,
        "decision_id": decision_id,
    }
    if query is not None:
        state["query"] = query

    broker = _build_broker(user, session, execution_enabled)
    repo = ExecutionRepo(session)
    graph = build_graph(broker, repo, guardrail_cfg())
    cfg = {"configurable": {"thread_id": decision_id}}
    return graph.invoke(state, config=cfg)
