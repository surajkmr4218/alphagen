"""add evidence to decisions

Persist the evidence bundle (diff + passages + signals) on the Decision row so the
Week-7 dashboard trail endpoint reads one row, independent of LangGraph checkpoint
retention. Server default '{}' backfills existing rows; write_decision populates it
for new runs.

Revision ID: a9b8c7d6e5f4
Revises: b7e1c2d3f4a5
Create Date: 2026-07-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9b8c7d6e5f4'
down_revision: Union[str, Sequence[str], None] = 'b7e1c2d3f4a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'decisions',
        sa.Column('evidence', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('decisions', 'evidence')
