"""chunks.text_sha + unique (filing_id, section, text_sha)

Re-running ingestion appended duplicate chunk rows (no uniqueness), which double-counts in
retrieval and silently corrupts eval runs. Add a content hash, backfill it, delete duplicates
keeping the lowest id per triple, then enforce uniqueness. The hash also lets the eval golden
set resolve labels by content instead of by row id.

Revision ID: b1c2d3e4f5a6
Revises: 30eabb9df3b3
Create Date: 2026-09-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = '30eabb9df3b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('chunks', sa.Column('text_sha', sa.String(length=32), nullable=True))
    op.execute("UPDATE chunks SET text_sha = md5(text)") # compute md5 hash of existing chunks
    # For any rows sharing the exact same (filing_id, section, text_sha), 
    # any copy with a higher primary key (c.id > d.id) is deleted..
    op.execute(
        """
        DELETE FROM chunks c
        USING chunks d
        WHERE c.filing_id = d.filing_id
          AND c.section = d.section
          AND c.text_sha = d.text_sha
          AND c.id > d.id
        """
    )
    op.alter_column('chunks', 'text_sha', nullable=False) # enforce non-null now
    
    # no two rows can have the same combination of filing_id, section, text_sha
    op.create_index(
        'uq_chunks_filing_section_sha', 'chunks',
        ['filing_id', 'section', 'text_sha'], unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_chunks_filing_section_sha', table_name='chunks')
    op.drop_column('chunks', 'text_sha')
