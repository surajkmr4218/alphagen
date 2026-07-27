from __future__ import annotations

import asyncio
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

from app.security import owner_token_storage

MCP_URL = "https://agent.robinhood.com/mcp/trading"

# Local loopback the OAuth redirect comes back to. The port must be free; if the
# auth server rejects this redirect_uri, that's a finding (Robinhood may pin its own).
CALLBACK_PORT = 8765
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}/callback"

# ---- OAuth interaction handlers ---------------------------------------------
async def redirect_handler(auth_url: str) -> None:
    """Open the system browser at the authorization URL."""
    print(f"\n→ Opening browser for Robinhood authorization:\n  {auth_url}\n")
    webbrowser.open(auth_url)


class _CallbackHandler(BaseHTTPRequestHandler):
    """One-shot HTTP handler that captures ?code=...&state=... from the redirect."""

    captured: dict[str, str | None] = {}

    def do_GET(self) -> None:  # noqa: N802 — stdlib-mandated method name
        params = parse_qs(urlparse(self.path).query)
        _CallbackHandler.captured = {
            "code": params.get("code", [None])[0],
            "state": params.get("state", [None])[0],
            "error": params.get("error", [None])[0],
        }
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h2>Authorization received. You can close this tab.</h2>")

    def log_message(self, *args) -> None:  # silence per-request stderr logging
        pass


async def callback_handler() -> tuple[str, str | None]:
    """Block (off the event loop) until the browser hits our redirect URI."""

    def serve_once() -> None:
        try:
            server = HTTPServer(("localhost", CALLBACK_PORT), _CallbackHandler)
        except OSError as e:
            raise RuntimeError(
                f"Port {CALLBACK_PORT} is already in use — most likely a previous run of "
                f"this script is still holding it (did you Ctrl+Z instead of Ctrl+C?). "
                f"Free it with:  lsof -ti :{CALLBACK_PORT} | xargs kill -9"
            ) from e
        try:
            server.handle_request()  # handles exactly one request, then returns
        finally:
            server.server_close()

    await asyncio.get_running_loop().run_in_executor(None, serve_once) # non-blocking
    captured = _CallbackHandler.captured
    if captured.get("error"):
        raise RuntimeError(f"Authorization failed: {captured['error']}")
    code = captured.get("code")
    if not code:
        raise RuntimeError("No authorization code received on the callback.")
    return code, captured.get("state")


async def main() -> None:
    # PRIMARY storage is now the encrypted per-user DB row (DbTokenStorage), same as prod.
    with owner_token_storage() as storage:
        # Observability for the gating question: announce whether we START with a token.
        existing = await storage.get_tokens()
        if existing is not None:
            print("[run #2 indicator] Found a persisted token in the DB — "
                  "if this run does NOT re-prompt, that's evidence for PATH A.")
        else:
            print("[run #1 indicator] No persisted token in the DB yet — "
                  "expect a browser auth prompt now.")

        client_metadata = OAuthClientMetadata(
            client_name="AlphaGen Spike",
            redirect_uris=[REDIRECT_URI],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method="none",  # public client (no secret); needs DCR support
        )

        auth = OAuthClientProvider(
            server_url=MCP_URL,
            client_metadata=client_metadata,
            storage=storage,
            redirect_handler=redirect_handler,
            callback_handler=callback_handler,
        )

        async with httpx.AsyncClient(
            auth=auth,
            follow_redirects=True,
            timeout=httpx.Timeout(30.0, read=300.0),
        ) as http_client:
            async with streamable_http_client(MCP_URL, http_client=http_client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    tools = await session.list_tools()
                    names = [t.name for t in tools.tools]
                    print(f"\nconnected. {len(names)} tools:")
                    for n in sorted(names):
                        print(f"  - {n}")

                    # find the order-placing tool and dump its schema verbatim
                    order_tool = next(
                        (t for t in tools.tools if "order" in t.name.lower()
                         and "place" in t.name.lower()),
                        None,
                    )
                    if order_tool is None:
                        order_tool = next(
                            (t for t in tools.tools if "order" in t.name.lower()), None)

                    if order_tool is not None:
                        print(f"\nORDER TOOL: {order_tool.name}")
                        print("inputSchema:")
                        print(json.dumps(order_tool.inputSchema, indent=2))
                    else:
                        print("\nNO order tool found — inspect the full list above.")


if __name__ == "__main__":
    asyncio.run(main())
