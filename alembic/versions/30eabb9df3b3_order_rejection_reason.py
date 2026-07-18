"""order rejection reason

Revision ID: 30eabb9df3b3
Revises: a9b8c7d6e5f4
Create Date: 2026-07-08 18:50:41.136236

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '30eabb9df3b3'
down_revision: Union[str, Sequence[str], None] = 'a9b8c7d6e5f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Why an execution was rejected (e.g. "check_twice: market CLOSED at execution").
    # Previously only the LangGraph checkpoint held this — invisible on the dashboard.
    op.add_column("orders", sa.Column("reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "reason")
