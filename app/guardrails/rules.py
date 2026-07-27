from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

# Schema fields a hypothesis MUST carry to be evaluable at all.
_REQUIRED = ("direction", "order_type", "size_usd", "confidence", "citations")


@dataclass
class R:
    """One rule result. severity is 'hard' (blocks) or 'soft' (warns)."""
    rule: str
    passed: bool
    severity: Literal["hard", "soft"]      
    reason: str


def _citations_resolve(h: dict, evidence: dict) -> bool:
    """Deterministic citation check: every cited (accession, section) must exist in the
    evidence bundle. Catches all hallucinated sources. """
    passages = evidence.get("passages", []) if evidence else []
    available = {(p.get("accession"), p.get("section")) for p in passages}
    cites = h.get("citations") or []
    if not cites:
        return False
    return all((c.get("accession"), c.get("section")) in available for c in cites)


def validate(
    h: dict,
    account: dict,
    today: date,
    evidence: dict,
    cfg: dict,
    *,
    live_price: float | None = None,
    market_open: bool | None = None,
) -> dict:
    """PURE function. No DB, no clock, no network — caller injects everything.

    h:        the hypothesis JSON (hypothesis_node output)
    account:  {"deployed": float, "trades_today": int, "pnl_today": float}
    today:    the as-of date (injected so backtest/tests control time)
    evidence: the evidence bundle (for citation resolution)
    cfg:      guardrail_cfg() thresholds

    Keyword-only, injected ONLY at the execution check-twice (both default None):
    live_price:  the FRESH broker quote — enables the price_sanity rule.
    market_open: the FRESH market-state boolean — enables the market_hours rule.
    When either is None its rule is simply not evaluated, so the guardrail node and the
    offline tests (which pass neither) see the exact same 8-rule result as before.

    Returns {"passed": bool, "results": [R, ...]}. EVERY (applicable) rule is evaluated and
    recorded; we never short-circuit. passed = all HARD rules passed.
    """
    results: list[R] = []

    # 1. schema (hard) — without required keys nothing else is meaningful.
    missing = [k for k in _REQUIRED if k not in h]
    results.append(R(
        "schema", not missing, "hard",
        "ok" if not missing else f"missing keys: {missing}",
    ))

    # 2. citations (hard) — every cited span must resolve in the evidence bundle.
    cites_ok = _citations_resolve(h, evidence)
    results.append(R(
        "citations", cites_ok, "hard",
        "all citations resolve" if cites_ok else "unresolved or empty citation",
    ))

    size = float(h.get("size_usd", 0.0) or 0.0)

    # 3. position_cap (hard) — one order may not exceed max_notional ($5).
    cap_ok = size <= cfg["max_notional"]
    results.append(R(
        "position_cap", cap_ok, "hard",
        f"size_usd {size} <= max_notional {cfg['max_notional']}"
        if cap_ok else f"size_usd {size} OVER cap {cfg['max_notional']}",
    ))

    # 4. confidence (SOFT) — below the floor warns but does NOT block.
    conf = float(h.get("confidence", 0.0) or 0.0)
    conf_ok = conf >= cfg["min_conf"]
    results.append(R(
        "confidence", conf_ok, "soft",
        f"confidence {conf} >= {cfg['min_conf']}"
        if conf_ok else f"LOW confidence {conf} < {cfg['min_conf']} (allowed, flagged)",
    ))

    # 5. allowlist (hard) — only vetted, liquid tickers may trade.
    ticker = (h.get("ticker") or account.get("ticker") or "").upper()
    allow_ok = ticker in {t.upper() for t in cfg["allowlist"]}
    results.append(R(
        "allowlist", allow_ok, "hard",
        f"{ticker} on allowlist" if allow_ok else f"{ticker} NOT on allowlist",
    ))

    # 6. rate_limit (hard) — cooldown: no more than max_per_day trades opened today.
    rate_ok = int(account.get("trades_today", 0)) < cfg["max_per_day"]
    results.append(R(
        "rate_limit", rate_ok, "hard",
        f"{account.get('trades_today', 0)} < {cfg['max_per_day']} today"
        if rate_ok else f"rate limit hit ({cfg['max_per_day']}/day)",
    ))

    # --- time-sensitive rules: only at the execution check-twice ---------------
    # These re-check conditions that move BETWEEN the guardrail node and the human's click,
    # so they run on the FRESH quote/market-state, not the stale ones the hypothesis was
    # written against. Skipped entirely (not recorded) when their input is None.

    # 7. market_hours (hard) — never place into a closed market.
    if market_open is not None:
        results.append(R(
            "market_hours", bool(market_open), "hard",
            "market open" if market_open else "market CLOSED at execution",
        ))

    # 8. price_sanity (hard) — the fresh quote must be a usable positive number before
    #     execute.py divides size_usd by it (a 0.0 would be a divide-by-zero / absurd qty).
    if live_price is not None:
        price_ok = live_price > 0
        results.append(R(
            "price_sanity", price_ok, "hard",
            f"live price {live_price} > 0" if price_ok else f"bad live price {live_price!r}",
        ))

    passed = all(r.passed for r in results if r.severity == "hard")
    return {"passed": passed, "results": [r.__dict__ for r in results]}