from __future__ import annotations

from datetime import UTC, datetime


def write_decision(db, state: dict, user_id: str = "owner") -> str:
    """Persist the full reasoning trail for one pipeline run. Returns decision_id."""
    from app.models import Decision, Order

    h = state.get("hypothesis") or {}
    guard = state.get("guardrail") or {}
    did = state["decision_id"]

    dec = Decision(
        decision_id=did,
        ticker=state["ticker"],
        evidence=state.get("evidence") or {},
        hypothesis=h,
        critic_verdict=state.get("critic_verdict"),
        guardrail=guard,                       # {passed, results} — the full rule trail
        passed=bool(guard.get("passed")),
        user_id=user_id,
        created_at=datetime.now(UTC),
    )
    db.merge(dec)           # merge so if row with decision_id exists, row gets replaced

    # A pending Order row only if the trade is eligible (passed). 
    if guard.get("passed"):
        db.merge(Order(
            decision_id=did, user_id=user_id, symbol=state["ticker"],
            side="buy", order_type=h.get("order_type", "limit"),
            size_usd=float(h.get("size_usd", 0.0)),
            limit_price=h.get("limit_price"),
            status="pending",                  # -> 'filled'/'rejected' at execution
            created_at=datetime.now(UTC),
        ))
    db.commit()
    return did