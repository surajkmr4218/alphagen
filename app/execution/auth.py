from __future__ import annotations

from mcp.client.auth import OAuthClientProvider
from mcp.client.auth import TokenStorage
from mcp.shared.auth import OAuthClientMetadata

MCP_URL = "https://agent.robinhood.com/mcp/trading"
# Redirect URI is only used during a *first* interactive auth (dev). Prod reuses the DB token.
REDIRECT_URI = "http://localhost:8765/callback"


async def _no_browser(*_a, **_k):
    """Redirect/callback handler that accepts any args but ignores them."""
    raise RuntimeError(
        "Robinhood OAuth needs interactive login, but this process is headless. "
        "Re-link the account (run the Session-0 spike locally) so a refreshable token "
        "lands in the DB."
    )


def robinhood_provider(storage: TokenStorage) -> OAuthClientProvider:
    return OAuthClientProvider(
        server_url=MCP_URL,
        client_metadata=OAuthClientMetadata(
            client_name="AlphaGen",
            redirect_uris=[REDIRECT_URI],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method="none",
        ),
        storage=storage,           # DbTokenStorage(db, user) — encrypted per-user token
        redirect_handler=_no_browser,
        callback_handler=_no_browser,
    )