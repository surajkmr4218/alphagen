from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from app.execution.dal import ExecutionRepo

# Reuse the Week-5 deterministic guardrails. Only a subset is time-sensitive.
from app.guardrails.rules import validate

# Hypothesis order_type -> place_equity_order 'type'. Long-only cash account.
_TYPE_MAP = {"market": "market", "limit": "limit", "stop": "stop_market"}

async def execution_node(
    state: dict[str, Any], broker: Any, db: ExecutionRepo, cfg: Any
) -> dict[str, Any]:
    """Deterministic execution. Never raises — broker/tool errors become a rejected Order.
    Injected broker/db/cfg keep this testable and let paper mode swap in a stub broker."""
    decision_id = state["decision_id"]
    h = state["hypothesis"]
    symbol = h["ticker"] if "ticker" in h else state["ticker"]

    # 3. Idempotency FIRST so a replayed resume can't double-place.
    existing = db.order_exists(decision_id)
    if existing:
        return {"order": existing}

    try:
        # 1. Live quote (fail-fast on a bad price inside the broker).
        price = await broker.get_quote(symbol)

        # 2. CHECK-TWICE: re-validate time-sensitive rules on the fresh quote + market state.
        account = db.get_account_snapshot(state.get("clerk_user_id"), state["ticker"])
        recheck = validate(
            h,
            account=account,
            today=date.today(),
            evidence=state["evidence"],
            cfg=cfg,
            live_price=price,            # price-sanity uses the FRESH price
            market_open=broker.market_open(),
        )
        if not recheck["passed"]:
            reasons = [
                r["reason"]
                for r in recheck["results"]
                if not r["passed"] and r["severity"] == "hard"
            ]
            order = {"status": "rejected", "reason": "check_twice: " + "; ".join(reasons)}
            db.write_order(decision_id, order)
            return {"order": order, "guardrail": recheck}

        # 4. notional -> quantity (fractional shares, market + regular_hours).
        qty = round(float(h["size_usd"]) / price, 4)
        if qty <= 0:
            raise ValueError(
                f"computed non-positive quantity from size_usd={h['size_usd']} price={price}"
            )

        # 5. field -> order mapping (deterministic; strings per the captured schema).
        otype = _TYPE_MAP[h["order_type"]]
        args: dict[str, Any] = {
            "symbol": symbol,
            "side": "buy",                       # long-only
            "type": otype,
            "quantity": f"{qty:.4f}",
            "time_in_force": "gfd",
            "market_hours": "regular_hours",
            "ref_id": str(uuid.uuid5(uuid.NAMESPACE_OID, decision_id)),  # stable per decision
        }
        if otype == "limit":
            args["limit_price"] = f"{float(h['limit_price']):.2f}"
        elif otype == "stop_market":
            # reuse the limit_price field as the stop price
            args["stop_price"] = f"{float(h['limit_price']):.2f}"

        # 6. place.
        result = await broker.place_order(**args)

        # 7. store success.
        order = {
            "broker_order_id": result.get("id") or result.get("order_id"),
            "status": result.get("state", "submitted"),
            "symbol": symbol,
            "side": "buy",
            "order_type": otype,
            "quantity": qty,
            "submitted_price": price,
            "ref_id": args["ref_id"],
            "reason": None,
        }
        db.write_order(decision_id, order)
        return {"order": order}

    except Exception as exc:  # noqa: BLE001 — the graph must NEVER crash on a broker error.
        order = {"status": "rejected", "reason": f"{type(exc).__name__}: {exc}"}
        db.write_order(decision_id, order)
        return {"order": order}