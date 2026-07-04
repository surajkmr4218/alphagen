"""One-shot: migrate the dev plaintext .robinhood_token.json into the encrypted DB.

Run once after switching storage to DbTokenStorage, so the currently-valid token +
client registration carry over and you skip a fresh browser login.

  uv run python -m scripts.seed_token_from_file
"""
from __future__ import annotations

import asyncio

from app.security import owner_token_storage
from scripts.spike_robinhood import FileTokenStorage


async def main() -> None:
    file_store = FileTokenStorage()
    tokens = await file_store.get_tokens()
    client = await file_store.get_client_info()

    if tokens is None:
        print("No tokens in .robinhood_token.json — nothing to import. Run the spike to auth.")
        return

    with owner_token_storage() as db_store:
        await db_store.set_tokens(tokens)
        if client is not None:
            await db_store.set_client_info(client)

    print("✓ Imported token"
          + (" + client registration" if client else "")
          + " into the encrypted DB (owner user). Re-run check_session0 — no browser expected.")


if __name__ == "__main__":
    asyncio.run(main())
