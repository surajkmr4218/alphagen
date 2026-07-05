from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from app.execution.dal import ExecutionRepo
from app.ingestion.fmp import eod_prices

log = logging.getLogger("reconcile")

async def _spy_return(db: ExecutionRepo, broker: Any, filled_at: dt.datetime) -> float | None:
    """SPY return over the trade's window (fill date -> now). None if either leg is unavailable."""
    try:
        spy_now = await broker.get_quote("SPY")
        rows = sorted(eod_prices(db.session, "SPY"), key=lambda r: r["date"], reverse=True)
        fill_day = filled_at.date()
        for row in rows:
            # First trading day at or before the fill date — a weekend/holiday fill
            # falls back to the prior close.
            if dt.date.fromisoformat(row["date"]) <= fill_day:
                base = float(row["price"])
                return (spy_now - base) / base
        return None
    except Exception as exc:  # noqa: BLE001 — benchmark is best-effort, never fail the sweep
        log.warning("spy return unavailable for window starting %s: %s", filled_at, exc)
        return None


async def reconcile_once(db, broker) -> None:
    # Pass 1 — fills: capture the fill price the instant an order fills, before it leaves _OPEN.
    for order in db.open_orders():
        try:
            st = await broker.order_status(order.broker_order_id)
        except Exception as exc:                        # noqa: BLE001 — never let cron die
            log.warning("status poll failed for %s: %s", order.broker_order_id, exc)
            continue
        state = st.get("state", order.status)
        fill_price = st.get("average_price") or st.get("executed_price")
        db.update_order_status(order.decision_id, state, fill_price)
        if state == "filled" and fill_price and not db.outcome_exists(order.decision_id):
            db.open_outcome(order, fill_price=float(fill_price))   # partial: returns stay NULL

    # Pass 2 — horizons: resolve any partial Outcome past its horizon, regardless of order status.
    for oc, symbol, filled_at in db.outcomes_awaiting_resolution():
        exit_price = await broker.get_quote(symbol)
        fwd = (exit_price - oc.fill_price) / oc.fill_price
        spy = await _spy_return(db, broker, filled_at)  # SPY over the same window; None if n/a
        db.resolve_outcome(oc, forward_return=fwd, spy_return=spy)


def start_scheduler(db, broker):
    # Lazy import — APScheduler only loaded when the cron is actually started.
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    sched = AsyncIOScheduler()
    sched.add_job(reconcile_once, "interval", minutes=15, args=[db, broker],
                  id="reconcile", max_instances=1, coalesce=True)
    sched.start()
    return sched