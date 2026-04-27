"""add_parent_chunks

Revision ID: b5d3e2f1a8c9
Revises: a1b2c3d4e5f6
Create Date: 2026-04-27 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b5d3e2f1a8c9'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'kb_parent_chunks',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('kb_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('doc_id', sa.String(64), nullable=False),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('parent_index', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_kb_parent_chunks_kb_id', 'kb_parent_chunks', ['kb_id'])
    op.create_index('ix_kb_parent_chunks_doc_id', 'kb_parent_chunks', ['doc_id'])

    op.add_column('kb_chunks', sa.Column('parent_id', sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column('kb_chunks', 'parent_id')
    op.drop_index('ix_kb_parent_chunks_doc_id', table_name='kb_parent_chunks')
    op.drop_index('ix_kb_parent_chunks_kb_id', table_name='kb_parent_chunks')
    op.drop_table('kb_parent_chunks')
