from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Decision, Order, Outcome, User


class ExecutionRepo:
    """Data-access layer the execution graph writes through.

    Wraps ONE SQLAlchemy Session behind the domain verbs that execute.py calls (and, in later
    sessions, the approval endpoints and the reconciliation job). Business code never issues
    raw ORM queries — it calls named methods — which keeps the query logic in one place and
    lets tests inject a fake repo with the same surface.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self._OPEN = {"queued", "submitted", "confirmed", "partially_filled", "pending"}

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
    
    def role_of(self, user: User) -> str:
        return user.role

    def decisions_pending(self, user: User):
        # Decisions whose human_decision is still 'pending', scoped to the tenant by RLS.
        return self.session.scalars(
            select(Decision).where(Decision.user_id == user.clerk_user_id,
                                   Decision.human_decision == "pending")
        ).all()

    def set_human_decision(self, decision_id: str, verdict: str, user, reason: str = "") -> None:
        dec = self.session.get(Decision, decision_id)
        if dec is not None:
            dec.human_decision = verdict         # 'approved' | 'rejected'
            self.session.commit()

    def open_orders(self):
        return self.session.scalars(
            select(Order).where(Order.status.in_(self._OPEN), Order.broker_order_id.isnot(None))
        ).all()

    def update_order_status(self, decision_id: str, state: str, fill_price=None) -> None:
        o = self.session.get(Order, decision_id)
        if o is not None:
            o.status = state           # the fill price is recorded on the Outcome, not the Order
            self.session.commit()

    def outcome_exists(self, decision_id: str) -> bool:
        return (self.session.scalar(
            select(func.count()).select_from(Outcome).where(Outcome.decision_id == decision_id)
        ) or 0) > 0

    def horizon_days(self, order) -> int:
        return 5  # default holding horizon; per-hypothesis override lands in Week 8

    def open_outcome(self, order, *, fill_price: float) -> None:
        # Partial write on first-seen fill. forward_return / spy_return / resolved_at stay NULL;
        # this is what survives the order leaving _OPEN. outcome_exists() guards against duplicates.
        self.session.merge(Outcome(
            decision_id=order.decision_id, user_id=order.user_id,
            fill_price=fill_price, horizon_days=self.horizon_days(order),
        ))
        self.session.commit()

    def outcomes_awaiting_resolution(self):
        # Partial Outcomes whose horizon has elapsed — NOT gated on order status (the whole point).
        # Join Order for the symbol + fill time (Outcome carries neither).
        now = datetime.now(UTC)
        return self.session.execute(
            select(Outcome, Order.symbol, Order.created_at)
            .join(Order, Order.decision_id == Outcome.decision_id)
            .where(
                Outcome.forward_return.is_(None),
                Order.created_at + func.make_interval(0, 0, 0, Outcome.horizon_days) <= now,
            )
        ).all()

    def resolve_outcome(self, outcome, *, forward_return: float, spy_return: float | None) -> None:
        outcome.forward_return = forward_return
        outcome.spy_return = spy_return           # first time anything populates this column
        outcome.resolved_at = datetime.now(UTC)
        self.session.commit()

    # --- consumed by the dashboard read endpoints (Session 6) ------------------
    # No explicit user_id filters here: the session's RLS GUC (app.user_id) already
    # scopes decisions/orders/outcomes to one tenant — another tenant's rows are invisible.
    def list_decisions(self, limit: int = 20) -> list[Decision]:
        return list(self.session.scalars(
            select(Decision).order_by(Decision.created_at.desc()).limit(limit)
        ))

    def get_decision(self, decision_id: str) -> Decision | None:
        return self.session.get(Decision, decision_id)

    def get_order(self, decision_id: str) -> dict | None:
        o = self.session.get(Order, decision_id)
        return _order_to_dict(o) if o else None

    def eval_summary(self) -> dict:
        """Live performance from resolved Outcomes."""
        resolved = list(self.session.scalars(
            select(Outcome).where(Outcome.forward_return.isnot(None))
        ))
        pending = self.session.scalar(
            select(func.count()).select_from(Outcome).where(Outcome.forward_return.is_(None))
        ) or 0
        n = len(resolved)
        excess = [o.forward_return - o.spy_return for o in resolved if o.spy_return is not None]
        return {
            "n_resolved": n,
            "n_pending": pending,
            "hit_rate": sum(o.forward_return > 0 for o in resolved) / n if n else None,
            "avg_return": sum(o.forward_return for o in resolved) / n if n else None,
            "avg_excess_vs_spy": sum(excess) / len(excess) if excess else None,
        }


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
