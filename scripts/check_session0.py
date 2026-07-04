"""Week-7 Session 0 preflight — verifies all three prerequisites in one run.

  1. Account is funded + agentic_allowed=true      (get_accounts + get_portfolio)
  2. Path A holds: cached token reused, NO browser  (spike token storage)
  3. place_equity_order inputSchema matches frozen   (list_tools)

Run:  uv run python scripts/check_session0.py
Exits non-zero if any check fails, so it doubles as a CI/gate.
"""
from __future__ import annotations

import asyncio
import json
import sys

import httpx
from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import OAuthClientMetadata

# Reuse the exact plumbing the Week-1 spike proved out.
from app.security import owner_token_storage
from scripts.spike_robinhood import (
    MCP_URL,
    REDIRECT_URI,
    callback_handler,
    redirect_handler,
)

MIN_FUNDING = 50.0  # Week-7 requires the $50 spike account

# Frozen schema field set from docs/week-7.md Session 0, step 3.
EXPECTED_FIELDS = {
    "account_number", "symbol", "side", "type", "quantity", "dollar_amount",
    "limit_price", "stop_price", "time_in_force", "market_hours", "ref_id",
}


def _text(result) -> str:
    """Pull the JSON text payload out of an MCP tool result."""
    return result.content[0].text


async def main() -> int:
    # PRIMARY storage: the encrypted per-user DB row (DbTokenStorage), same path as prod.
    with owner_token_storage() as storage:
        had_token = await storage.get_tokens() is not None
        if not had_token:
            print("✗ CHECK 2 (Path A): no token stored in the DB — "
                  "a browser prompt is about to appear. That is a re-auth, not reuse.")
        else:
            print("• stored token present — connecting; expect NO browser prompt...")

        auth = OAuthClientProvider(
            server_url=MCP_URL,
            client_metadata=OAuthClientMetadata(
                client_name="AlphaGen Session0 Check",
                redirect_uris=[REDIRECT_URI],
                grant_types=["authorization_code", "refresh_token"],
                response_types=["code"],
                token_endpoint_auth_method="none",
            ),
            storage=storage,
            redirect_handler=redirect_handler,
            callback_handler=callback_handler,
        )

        failures: list[str] = []

        # New MCP SDK: attach the OAuth provider (an httpx.Auth) to the httpx client;
        # the transport no longer accepts `auth=`.
        async with httpx.AsyncClient(
            auth=auth,
            follow_redirects=True,
            timeout=httpx.Timeout(30.0, read=300.0),
        ) as http_client:
            async with streamable_http_client(MCP_URL, http_client=http_client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    print("✓ CHECK 2 (Path A): connected via streamable HTTP.")
                    if had_token:
                        print("  (token reused — if no browser opened above, Path A confirmed.)")

                    # --- CHECK 1a: agentic account exists -------------------
                    accts = json.loads(_text(await session.call_tool("get_accounts", {})))
                    accounts = accts["data"]["accounts"]
                    agentic = [a for a in accounts if a.get("agentic_allowed")]
                    print("\n--- accounts ---")
                    for a in accounts:
                        tag = "  <-- AGENTIC" if a.get("agentic_allowed") else ""
                        print(f"  {a.get('nickname', a['brokerage_account_type']):12} "
                              f"{a['account_number']}  agentic={a['agentic_allowed']}{tag}")

                    if not agentic:
                        failures.append("CHECK 1: no account with agentic_allowed=true "
                                        "(is this the agent your phone shows as connected?)")
                        acct_num = None
                    elif len(agentic) > 1:
                        failures.append(f"CHECK 1: {len(agentic)} agentic accounts — ambiguous.")
                        acct_num = agentic[0]["account_number"]
                    else:
                        acct_num = agentic[0]["account_number"]
                        print(f"\n✓ CHECK 1a: agentic account = {acct_num}")

                    # --- CHECK 1b: funded >= $50 ---------------------------
                    if acct_num:
                        pf = json.loads(_text(await session.call_tool(
                            "get_portfolio", {"account_number": acct_num})))
                        print("\n--- portfolio (raw) ---")
                        print(json.dumps(pf, indent=2)[:1200])
                        # Balance field name can drift; surface it, don't hard-parse blindly.
                        equity = _find_balance(pf)
                        if equity is None:
                            failures.append("CHECK 1b: could not locate a balance field in "
                                            "get_portfolio output — inspect the raw dump above.")
                        elif equity < MIN_FUNDING:
                            failures.append(
                                f"CHECK 1b: balance ${equity:.2f} < ${MIN_FUNDING:.0f} "
                                "— fund the Agentic account on your phone/desktop.")
                        else:
                            print(f"\n✓ CHECK 1b: funded ${equity:.2f} (>= ${MIN_FUNDING:.0f})")

                    # --- CHECK 3: frozen place_equity_order schema ---------
                    tools = await session.list_tools()
                    place = next((t for t in tools.tools
                                  if t.name == "place_equity_order"), None)
                    if place is None:
                        failures.append("CHECK 3: place_equity_order tool not exposed.")
                    else:
                        props = set((place.inputSchema or {}).get("properties", {}).keys())
                        missing = EXPECTED_FIELDS - props
                        extra = props - EXPECTED_FIELDS
                        print("\n--- place_equity_order inputSchema ---")
                        print(json.dumps(place.inputSchema, indent=2))
                        if missing:
                            failures.append(
                                f"CHECK 3: schema DRIFTED — missing fields: {sorted(missing)}")
                        else:
                            print(f"\n✓ CHECK 3: all {len(EXPECTED_FIELDS)} frozen fields present.")
                        if extra:
                            print(f"  note: {len(extra)} new field(s) since freeze: "
                                  f"{sorted(extra)}")

        print("\n" + "=" * 60)
        if failures:
            print("SESSION 0 NOT READY:")
            for f in failures:
                print(f"  ✗ {f}")
            return 1
        print("SESSION 0 READY ✓  — all prerequisites confirmed.")
        return 0


def _find_balance(payload) -> float | None:
    """Best-effort scan for a cash/equity balance in the portfolio payload."""
    keys = ("total_value", "cash", "total_equity", "equity", "portfolio_equity")
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for k, v in node.items():
                if k in keys:
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        pass
                stack.append(v)
        elif isinstance(node, list):
            stack.extend(node)
    return None


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
