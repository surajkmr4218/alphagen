from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Decision, Order, Outcome, User


class ExecutionRepo:
    """Data-access layer the execution graph writes through.

    Wraps ONE SQLAlchemy Session behind the domain verbs that execute.py calls (and, in later
    sessions, the approval endpoints and the reconciliation job). Business code never issues
    raw ORM queries. It calls named methods, which keeps the query logic in one place and
    lets tests inject a fake repo with the same surface.

    `user_id` is the tenant scope for the read verbs: request-bound repos MUST pass it —
    this explicit WHERE scoping is the isolation layer. None means a trusted system
    session (execution node, reconcile cron) that legitimately sees every tenant's rows.
    """

    def __init__(self, session: Session, user_id: str | None = None) -> None:
        self.session = session
        self.user_id = user_id
        self._OPEN = {"queued", "submitted", "confirmed", "partially_filled", "pending"}

    def _scoped(self, stmt, col):
        """Append the tenant predicate unless this is an unscoped system repo."""
        return stmt.where(col == self.user_id) if self.user_id is not None else stmt

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
        # A fresh row (placeholder invisible or never written) must carry the tenant key.
        o = self.session.get(Order, decision_id) or Order(
            decision_id=decision_id, user_id=self.user_id
        )
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
        if order.get("size_usd") is not None:
            o.size_usd = float(order["size_usd"])
        if order.get("reason") is not None:
            o.reason = order["reason"]
        self.session.merge(o)
        self.session.commit()

    def update_guardrail(self, decision_id: str, guardrail: dict) -> None:
        """Replace the decision's guardrail trail with the execution-time CHECK-TWICE result.

        log_node persisted the hypothesis-time pass, but the rules that actually block an
        approved order (market_hours, price_sanity) only run at execution — without this the
        dashboard shows all-PASS while the order sits rejected."""
        dec = self.session.get(Decision, decision_id)
        if dec is not None:
            dec.guardrail = guardrail
            dec.passed = bool(guardrail.get("passed"))
            self.session.commit()

    def get_account_snapshot(self, user_id: str | None, ticker: str) -> dict:
        """Deterministic account facts validate() needs: {deployed, trades_today, pnl_today}.

        Positions/PnL are 0.0 until live broker positions are wired; the trade count
        is real, from today's Order rows.
        """
        return {
            "ticker": ticker,                               
            "deployed": 0.0,                             
            "trades_today": self._trades_today(user_id),  
            "pnl_today": 0.0,                             
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
        # Decisions whose human_decision is still 'pending', scoped to the tenant explicitly.
        return self.session.scalars(
            select(Decision).where(Decision.user_id == user.clerk_user_id,
                                   Decision.human_decision == "pending")
        ).all()

    def set_human_decision(self, decision_id: str, verdict: str, user, reason: str = "") -> None:
        dec = self.session.get(Decision, decision_id)
        if dec is not None:
            dec.human_decision = verdict          
            self.session.commit()

    def open_orders(self):
        return self.session.scalars(
            select(Order).where(Order.status.in_(self._OPEN), Order.broker_order_id.isnot(None))
        ).all()

    def update_order_status(self, decision_id: str, state: str, fill_price=None) -> None:
        o = self.session.get(Order, decision_id)
        if o is not None:
            o.status = state            
            self.session.commit()

    def outcome_exists(self, decision_id: str) -> bool:
        return (self.session.scalar(
            select(func.count()).select_from(Outcome).where(Outcome.decision_id == decision_id)
        ) or 0) > 0

    def horizon_days(self, order) -> int:
        return 5  # default holding horizon; per-hypothesis override lands 

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

    # --- consumed by the UI run-submission endpoints (dashboard upgrades) ----
    # Run state lives in Decision.human_decision: 'running' -> 'pending' (parked at the
    # approval gate) | 'rejected' (system-resolved: critic/guardrail/abstain) | 'failed'.
    def create_running_decision(self, decision_id: str, ticker: str, user_id: str) -> None:
        """Stub row inserted BEFORE the pipeline starts, so run status is DB-backed.

        write_decision's merge never sets human_decision on its transient instance, so
        'running' survives log_node while the JSON trail fields get filled in.
        """
        self.session.add(Decision(
            decision_id=decision_id, ticker=ticker.upper(), user_id=user_id,
            human_decision="running", evidence={}, hypothesis={}, critic_verdict={},
            guardrail={}, passed=False, created_at=datetime.now(UTC),
        ))
        self.session.commit()

    def active_run_for(self, ticker: str, *, stale_minutes: int = 30) -> Decision | None:
        """The in-flight run blocking this ticker, if any. Rows older than the staleness
        window don't count — a worker that died mid-run must not brick the ticker."""
        cutoff = datetime.now(UTC) - timedelta(minutes=stale_minutes)
        return self.session.scalars(
            self._scoped(select(Decision), Decision.user_id).where(
                Decision.ticker == ticker.upper(),
                Decision.human_decision == "running",
                Decision.created_at >= cutoff,
            )
        ).first()

    def pending_decisions_for(self, ticker: str) -> list[Decision]:
        """'pending' candidates for the one-active-run check. The caller must confirm each
        is actually parked at the execute interrupt (aget_state) — legacy critic-rejected
        rows sit at 'pending' forever without being parked and must not block."""
        return list(self.session.scalars(
            self._scoped(select(Decision), Decision.user_id).where(
                Decision.ticker == ticker.upper(), Decision.human_decision == "pending"
            )
        ))

    def mark_run_status(self, decision_id: str, status: str, *, reason: str | None = None) -> None:
        dec = self.session.get(Decision, decision_id)
        if dec is None:
            return
        dec.human_decision = status
        if reason and not dec.guardrail:
            # Guardrail-shaped so the existing ReasoningTrail UI renders the failure
            # without any new frontend field; /owner/runs reads the reason back from here.
            dec.guardrail = {
                "passed": False,
                "results": [{"rule": "pipeline", "passed": False,
                             "severity": "hard", "reason": reason[:500]}],
            }
        self.session.commit()

    def list_decisions(self, limit: int = 20) -> list[Decision]:
        return list(self.session.scalars(
            self._scoped(select(Decision), Decision.user_id)
            .order_by(Decision.created_at.desc()).limit(limit)
        ))

    def list_decisions_with_fills(
        self, limit: int = 20
    ) -> list[tuple[Decision, Order | None, Outcome | None]]:
        """Decisions newest-first with their order + outcome in ONE query (no N+1).
        Outcome has no uniqueness on decision_id, so dedupe to the first-seen row."""
        rows = self.session.execute(
            self._scoped(select(Decision, Order, Outcome), Decision.user_id)
            .outerjoin(Order, Order.decision_id == Decision.decision_id)
            .outerjoin(Outcome, Outcome.decision_id == Decision.decision_id)
            .order_by(Decision.created_at.desc())
            .limit(limit)
        ).all()
        seen: set[str] = set()
        out: list[tuple[Decision, Order | None, Outcome | None]] = []
        for dec, order, outcome in rows:
            if dec.decision_id in seen:
                continue
            seen.add(dec.decision_id)
            out.append((dec, order, outcome))
        return out

    def get_decision(self, decision_id: str) -> Decision | None:
        # Scoped select, not session.get: another tenant's decision_id must 404, not leak
        # its trail to whoever guesses the UUID.
        return self.session.scalars(
            self._scoped(select(Decision), Decision.user_id)
            .where(Decision.decision_id == decision_id)
        ).first()

    def get_order(self, decision_id: str) -> dict | None:
        o = self.session.scalars(
            self._scoped(select(Order), Order.user_id)
            .where(Order.decision_id == decision_id)
        ).first()
        return _order_to_dict(o) if o else None

    def eval_summary(self) -> dict:
        """Live performance from resolved Outcomes."""
        resolved = list(self.session.scalars(
            self._scoped(select(Outcome), Outcome.user_id)
            .where(Outcome.forward_return.isnot(None))
        ))
        pending = self.session.scalar(
            self._scoped(select(func.count()).select_from(Outcome), Outcome.user_id)
            .where(Outcome.forward_return.is_(None))
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
        "reason": o.reason,
        "broker_order_id": o.broker_order_id,
        "symbol": o.symbol,
        "side": o.side,
        "order_type": o.order_type,
        "size_usd": o.size_usd,
        "quantity": o.qty,
        "limit_price": o.limit_price,
    }
