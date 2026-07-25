"""oauth blob columns for DbTokenStorage

Adds two Fernet-encrypted columns the MCP OAuthClientProvider round-trips through
DbTokenStorage:
  - rh_oauth_token_enc:  full OAuthToken JSON (carries expires_in/scope/token_type
                         that the flat access/refresh columns drop — needed for refresh).
  - rh_oauth_client_enc: the dynamic-client-registration record, so a fresh process
                         reuses the registration instead of re-registering every run.

Revision ID: b7e1c2d3f4a5
Revises: 9f6b21b80a84
Create Date: 2026-07-02 15:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e1c2d3f4a5"
down_revision: Union[str, Sequence[str], None] = "dc5f45ab4851"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("rh_oauth_token_enc", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("rh_oauth_client_enc", sa.Text(), nullable=True))
    # The flat access/refresh columns are now redundant — the token blob contains both,
    # plus expires_in/scope. Drop them; get_robinhood_access_token reads from the blob.
    op.drop_column("users", "rh_access_token_enc")
    op.drop_column("users", "rh_refresh_token_enc")


def downgrade() -> None:
    op.add_column("users", sa.Column("rh_refresh_token_enc", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("rh_access_token_enc", sa.Text(), nullable=True))
    op.drop_column("users", "rh_oauth_client_enc")
    op.drop_column("users", "rh_oauth_token_enc")
