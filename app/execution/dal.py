from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Order


class ExecutionRepo:
    """Data-access layer the execution graph writes through.

    Wraps ONE SQLAlchemy Session behind the domain verbs that execute.py calls (and, in later
    sessions, the approval endpoints and the reconciliation job). Business code never issues
    raw ORM queries — it calls named methods — which keeps the query logic in one place and
    lets tests inject a fake repo with the same surface.

    Grows across the week:
      - Session 3 (here):  order_exists, write_order, get_account_snapshot, today_counters
      - Session 4 (approval):   role_of, decisions_pending, set_human_decision
      - Session 5 (reconcile):  open_orders, update_order_status, outcome_exists,
                                horizon_days, write_outcome
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    # --- consumed by execution_node (Session 2) -------------------------------
    def order_exists(self, decision_id: str) -> dict | None:
        """Return an already-PLACED order (for idempotency), or None.

        The 'pending' placeholder row that log_node writes does NOT count — execution must
        still run for it. Only a row that execution already acted on (status != 'pending')
        short-circuits a replayed resume.
        """
        o = self.session.get(Order, decision_id)
        return _order_to_dict(o) if o and o.status != "pending" else None

    def write_order(self, decision_id: str, order: dict[str, Any]) -> None:
        """Upsert the Order row for this decision with the execution result (or rejection)."""
        o = self.session.get(Order, decision_id) or Order(decision_id=decision_id)
        if order.get("status") is not None:
            o.status = order["status"]
        if order.get("broker_order_id") is not None:
            o.broker_order_id = order["broker_order_id"]
        if order.get("symbol"):
            o.symbol = order["symbol"]
        if order.get("side"):
            o.side = order["side"]
        if order.get("order_type"):
            o.order_type = order["order_type"]
        if order.get("quantity") is not None:
            o.qty = float(order["quantity"])
        self.session.merge(o)
        self.session.commit()

    def get_account_snapshot(self, user_id: str | None, ticker: str) -> dict:
        """Deterministic account facts validate() needs: {deployed, trades_today, pnl_today}.

        Positions/PnL are 0.0 until live broker positions are wired (Week 8); the trade count
        is real, from today's Order rows.
        """
        return {
            "ticker": ticker,                               
            "deployed": 0.0,                               # live positions -> Week 8
            "trades_today": self._trades_today(user_id),   # the REAL count
            "pnl_today": 0.0,                              # live positions -> Week 8
        }

    def today_counters(self, user_id: str | None) -> dict:
        """Today's rate-limit counters (trades opened today), scoped to the tenant."""
        return {"trades_today": self._trades_today(user_id)}

    def _trades_today(self, user_id: str | None) -> int:
        start = datetime.combine(date.today(), datetime.min.time(), tzinfo=UTC)
        stmt = select(func.count()).select_from(Order).where(Order.created_at >= start)
        if user_id:
            stmt = stmt.where(Order.user_id == user_id)
        return self.session.scalar(stmt) or 0


def _order_to_dict(o: Order) -> dict:
    return {
        "decision_id": o.decision_id,
        "status": o.status,
        "broker_order_id": o.broker_order_id,
        "symbol": o.symbol,
        "side": o.side,
        "order_type": o.order_type,
        "size_usd": o.size_usd,
        "quantity": o.qty,
        "limit_price": o.limit_price,
    }
