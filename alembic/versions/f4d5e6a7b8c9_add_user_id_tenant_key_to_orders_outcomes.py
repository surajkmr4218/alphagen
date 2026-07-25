"""add user_id tenant key to orders/outcomes (+ index decisions.user_id)

Every query scopes decisions/orders/outcomes by a per-user tenant key. decisions
already had user_id; add it to orders and outcomes and index it on all three.

Revision ID: f4d5e6a7b8c9
Revises: e3c4d5f6a7b8
Create Date: 2026-06-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4d5e6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'e3c4d5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('orders', sa.Column('user_id', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_orders_user_id'), 'orders', ['user_id'], unique=False)

    op.add_column('outcomes', sa.Column('user_id', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_outcomes_user_id'), 'outcomes', ['user_id'], unique=False)

    op.create_index(op.f('ix_decisions_user_id'), 'decisions', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_decisions_user_id'), table_name='decisions')

    op.drop_index(op.f('ix_outcomes_user_id'), table_name='outcomes')
    op.drop_column('outcomes', 'user_id')

    op.drop_index(op.f('ix_orders_user_id'), table_name='orders')
    op.drop_column('orders', 'user_id')
