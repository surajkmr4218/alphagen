from __future__ import annotations

import datetime as dt
import json
from typing import Any
from zoneinfo import ZoneInfo

import httpx

ET = ZoneInfo("America/New_York")
MCP_URL = "https://agent.robinhood.com/mcp/trading"


class RobinhoodBroker:
    """Thin wrapper over the Robinhood Trading MCP tools. Direct MCP via
    langchain-mcp-adapters. 

    `auth` is the OAuth handler (an httpx.Auth) — inject the OAuthClientProvider
    backed by DbTokenStorage. Without it the Robinhood MCP server 401s every call."""

    def __init__(self, account_number: str, auth: httpx.Auth) -> None:
        self.account_number = account_number
        self._auth = auth
        self._tools: dict[str, Any] | None = None

    async def _load_tools(self) -> dict[str, Any]:
        if self._tools is None:
            from langchain_mcp_adapters.client import MultiServerMCPClient

            client = MultiServerMCPClient(
                {"robinhood": {
                    "transport": "streamable_http",
                    "url": MCP_URL,
                    "auth": self._auth,  # OAuthClientProvider -> attaches/refreshes bearer token
                    # Robinhood rejects the DELETE session-teardown (returns 400). Skip it — it's noise.
                    "terminate_on_close": False,
                }}
            )
            tools = await client.get_tools()
            self._tools = {t.name: t for t in tools}
        return self._tools

    async def _call(self, name: str, **kwargs: Any) -> Any:
        tools = await self._load_tools()
        if name not in tools:
            raise RuntimeError(f"Robinhood MCP tool '{name}' not available")
        return await tools[name].ainvoke(kwargs)

    @staticmethod
    def _payload(res: Any) -> dict:
        """Unwrap an ainvoke result into the parsed JSON payload.

        langchain-mcp-adapters returns MCP *content blocks* (e.g. {"type":"text","text":...});
        the data we want is a JSON string inside the text block, and Robinhood nests it all
        under `data`. This flattens both layers so callers see one dict.

        A block can also carry plain text (an error/notice, or a summary preceding the JSON
        block). Return the first block that parses; if none do, raise with the raw text —
        it is the only record of what the broker said, and it must reach order.reason.
        """
        blocks = res if isinstance(res, list) else [res]
        texts = [b["text"] for b in blocks if isinstance(b, dict) and b.get("text")]
        for text in texts:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                continue
        if isinstance(res, dict) and "data" in res:  # already-structured fallback
            return res
        if texts:
            raise RuntimeError(f"broker returned non-JSON response: {' | '.join(texts)[:300]!r}")
        raise RuntimeError(f"unexpected MCP result shape: {res!r}")

    async def get_quote(self, symbol: str) -> float:
        res = await self._call("get_equity_quotes", symbols=[symbol])
        # Real shape: data.results[0].quote.<price>. Values are STRINGS. Prefer the regular
        # last trade, then the off-hours trade, then ask. Raise (never 0.0) if all absent.
        results = self._payload(res).get("data", {}).get("results") or []
        quote = (results[0].get("quote") if results else {}) or {}
        price = (quote.get("last_trade_price")
                 or quote.get("last_non_reg_trade_price")
                 or quote.get("ask_price"))
        if price is None:
            raise RuntimeError(f"no quote for {symbol}: {quote!r}")
        return float(price)

    async def tradable(self, symbol: str) -> bool:
        # get_equity_tradability REQUIRES account_number.
        res = await self._call(
            "get_equity_tradability", symbols=[symbol], account_number=self.account_number
        )
        results = self._payload(res).get("data", {}).get("results") or []
        row = results[0] if results else {}
        tradeable_str = row.get("tradeable", False)
        return tradeable_str.lower() == "true"

    def market_open(self, now: dt.datetime | None = None) -> bool:
        # Deterministic local check (no network): NYSE regular hours, Mon-Fri 09:30-16:00 ET.
        # Holidays are a known gap — see Known gaps.
        now = (now or dt.datetime.now(tz=ET)).astimezone(ET)
        if now.weekday() >= 5:
            return False
        open_t = now.replace(hour=9, minute=30, second=0, microsecond=0)
        close_t = now.replace(hour=16, minute=0, second=0, microsecond=0)
        return open_t <= now <= close_t

    async def place_order(self, **args: Any) -> dict[str, Any]:
        # args already mapped to the EXACT place_equity_order schema by execute.py.
        args.setdefault("account_number", self.account_number)
        res = await self._call("place_equity_order", **args)
        data = self._payload(res).get("data", {})
        # The created order is nested (data.order / data.orders[0] — same family as
        # get_equity_orders' data.orders). Reading id/state off `data` directly left
        # broker_order_id NULL, hiding the order from the reconcile sweep forever.
        if isinstance(data.get("order"), dict):
            return data["order"]
        if isinstance(data.get("orders"), list) and data["orders"]:
            return data["orders"][0]
        return data

    async def order_status(self, order_id: str) -> dict[str, Any]:
        # The get_equity_orders function takes order_id + account_number; results are data.orders.
        res = await self._call(
            "get_equity_orders", order_id=order_id, account_number=self.account_number
        )
        orders = self._payload(res).get("data", {}).get("orders") or []
        return orders[0] if orders else {}

    async def portfolio(self) -> dict[str, float | None]:
        # Account snapshot: {total_equity, cash, buying_power}.  
        res = await self._call("get_portfolio", account_number=self.account_number)
        data = self._payload(res).get("data", {})
        bp = data.get("buying_power")
        return {
            "total_equity": _to_float(data.get("total_value")),
            "cash": _to_float(data.get("cash")),
            "buying_power": _to_float(bp.get("buying_power") if isinstance(bp, dict) else bp),
        }


def _to_float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class StubBroker:
    """Paper-mode broker: deterministic fakes, no network, no real orders. Injected when
    execution is disabled (public tier) or in tests — includes async def functions, so
    the execution node can't tell the difference and no TypeErrors come up"""

    def __init__(self, account_number: str = "STUB") -> None:
        self.account_number = account_number

    async def get_quote(self, symbol: str) -> float:
        return 100.0

    async def tradable(self, symbol: str) -> bool:
        return True

    def market_open(self, now: dt.datetime | None = None) -> bool:
        return True

    async def place_order(self, **args: Any) -> dict[str, Any]:
        return {"id": f"STUB-{args.get('ref_id', 'x')}", "state": "filled", "_stub": True}

    async def order_status(self, order_id: str) -> dict[str, Any]:
        return {"id": order_id, "state": "filled", "_stub": True}

    async def portfolio(self) -> dict[str, float | None]:
        return {"total_equity": 50.0, "cash": 25.0, "buying_power": 25.0}