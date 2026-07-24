"""
Handles data ingestion from FMP (Financial Modeling Prep) API. 
Caches results in the database to avoid excessive API calls. 
Each type of data has a defined time-to-live (TTL) to determine freshness.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Signal

BASE = "https://financialmodelingprep.com/stable"

# How long a saved signal stays "fresh". Prices move intraday-ish; scores, consensus,
# and price targets barely move. Tune per-type if you blow the budget.
DEFAULT_TTL = dt.timedelta(hours=12)
TTL_BY_KIND: dict[str, dt.timedelta] = {
    "eod_prices": dt.timedelta(hours=12),
    "financial_scores": dt.timedelta(days=3),
    "analyst_consensus": dt.timedelta(days=3),
    "analyst_grades": dt.timedelta(days=3),
    "price_target_consensus": dt.timedelta(days=3),
}


def _get(path: str, **params: Any) -> Any:
    """Raw FMP GET. Adds the apikey. No caching here — callers go through _cached()."""
    params["apikey"] = settings.fmp_api_key
    with httpx.Client(timeout=30.0) as client:
        r = client.get(f"{BASE}/{path}", params=params)
        r.raise_for_status()
        return r.json()

def _fresh(row: Signal, kind: str) -> bool:
    ttl = TTL_BY_KIND.get(kind, DEFAULT_TTL)
    age = dt.datetime.now(dt.UTC) - row.fetched_at
    return age < ttl

def _cached(session: Session, ticker: str, kind: str, path: str, **params: Any) -> Any:
    """Return cached payload (in db) or fetch from FMP, persist to Signal, return."""
    stmt = (
        select(Signal)
        .where(Signal.ticker == ticker, Signal.kind == kind)
        .order_by(Signal.fetched_at.desc())
        .limit(1)
    )
    row = session.scalars(stmt).first()
    if row is not None and _fresh(row, kind):
        return row.payload  # cache hit — zero FMP calls

    payload = _get(path, **params)  # cache miss / stale — one FMP call
    session.add(Signal(ticker=ticker, kind=kind, payload=payload))
    session.commit()
    return payload

def financial_scores(session: Session, ticker: str) -> Any:
    """Altman Z-score, Piotroski F-score. Bullish tail = high Piotroski + safe Z."""
    return _cached(session, ticker, "financial_scores", "financial-scores", symbol=ticker)


def eod_prices(session: Session, ticker: str) -> list[dict]:
    """Light EOD history — used for price sanity + Week-5 backtest forward returns."""
    return _cached(
        session, ticker, "eod_prices", "historical-price-eod/light", symbol=ticker,
    )


def analyst_consensus(session: Session, ticker: str) -> Any:
    """grades-consensus: counts of strongBuy/buy/hold/sell/strongSell."""
    return _cached(session, ticker, "analyst_consensus", "grades-consensus", symbol=ticker)


def analyst_grades(session: Session, ticker: str, limit: int = 20) -> list[dict]:
    """Recent rating changes (upgrade/downgrade) by firm — bullish tail = upgrades."""
    return _cached(
        session, ticker, "analyst_grades", "grades", symbol=ticker, limit=limit,
    )


def price_target_consensus(session: Session, ticker: str) -> Any:
    """Analyst price targets (high/low/median/consensus). Bullish tail = consensus >> price."""
    return _cached(
        session, ticker, "price_target_consensus", "price-target-consensus", symbol=ticker,
    )

def price_target_upside(targets: Any, last_price: float | None) -> dict:
    """Reduce price-target-consensus to upside vs the latest close."""
    t = targets[0] if isinstance(targets, list) and targets else (targets or {})
    consensus = t.get("targetConsensus") or t.get("targetMedian")
    if not consensus or not last_price:
        return {"consensus": consensus, "upside": None, "bullish": False}
    upside = (float(consensus) - last_price) / last_price
    return {"consensus": float(consensus), "upside": round(upside, 3), "bullish": upside > 0}


def consensus_skew(consensus: Any) -> dict:
    """Reduce grades-consensus to a single bullish-skew float in [-1, 1]."""
    c = consensus[0] if isinstance(consensus, list) and consensus else (consensus or {})
    sb, b = float(c.get("strongBuy") or 0), float(c.get("buy") or 0)
    h = float(c.get("hold") or 0)
    s, ss = float(c.get("sell") or 0), float(c.get("strongSell") or 0)
    total = sb + b + h + s + ss
    if total == 0:
        return {"skew": 0.0, "n": 0}
    skew = (2 * sb + b - s - 2 * ss) / (2 * total)
    return {"skew": round(skew, 3), "n": int(total)}

def attach_signals(session: Session, ticker: str, bundle: dict) -> dict:
    """Take the evidence bundle and bolt a structured `signals` block onto it."""
    scores = financial_scores(session, ticker)
    prices = eod_prices(session, ticker)
    consensus = analyst_consensus(session, ticker)
    grades = analyst_grades(session, ticker, limit=10)
    targets = price_target_consensus(session, ticker)

    score = scores[0] if isinstance(scores, list) and scores else (scores or {})
    last_price = float(prices[0]["price"]) if isinstance(prices, list) and prices else None
    skew = consensus_skew(consensus)
    upside = price_target_upside(targets, last_price)

    bundle["signals"] = {
        "financial_scores": {
            "altman_z": score.get("altmanZScore"),
            "piotroski": score.get("piotroskiScore"),
        },
        "last_price": last_price,
        "analyst_consensus": skew,
        "recent_grades": [
            {"firm": g.get("gradingCompany"), "action": g.get("action"),
             "to": g.get("newGrade")}
            for g in (grades or [])[:5]
        ],
        "price_target": upside,
    }
    # Long-only convenience flag the hypothesis node reads directly.
    bundle["signals"]["bullish_tail"] = bool(
        upside["bullish"] or skew["skew"] > 0.2 or (score.get("piotroskiScore") or 0) >= 7
    )
    return bundle