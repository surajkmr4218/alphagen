from __future__ import annotations

import time
from typing import Any

# (live, ticker) -> (price_or_None, monotonic_ts). Keyed by tier so StubBroker's static
# quotes (public tier) never pollute the owner's live prices. Failures are cached as None
# for the same TTL: a broken MCP session must not re-handshake on every 30s dashboard poll.
_CACHE: dict[tuple[bool, str], tuple[float | None, float]] = {}
_TTL_SECONDS = 30.0


async def cached_quote(broker: Any, ticker: str, *, live: bool) -> float | None:
    """One broker.get_quote per (tier, ticker) per TTL window; None on failure, never raises."""
    key = (live, ticker.upper())
    hit = _CACHE.get(key)
    now = time.monotonic()
    if hit is not None and now - hit[1] < _TTL_SECONDS:
        return hit[0]
    try:
        price: float | None = float(await broker.get_quote(ticker.upper()))
    except Exception:  # noqa: BLE001 — a missing quote is a normal, non-fatal outcome
        price = None
    _CACHE[key] = (price, now)
    return price
