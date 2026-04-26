"""add_kb_chunks_table

Revision ID: a1b2c3d4e5f6
Revises: e8c7ceea96c7
Create Date: 2026-04-26 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'e8c7ceea96c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 启用 pg_trgm 扩展（幂等）
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        'kb_chunks',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('kb_id', sa.UUID(), nullable=False),
        sa.Column('doc_id', sa.String(length=64), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_kb_chunks_kb_id', 'kb_chunks', ['kb_id'])
    op.create_index('ix_kb_chunks_doc_id', 'kb_chunks', ['doc_id'])
    # pg_trgm GIN 索引，加速 similarity() 查询
    op.execute(
        "CREATE INDEX ix_kb_chunks_content_trgm "
        "ON kb_chunks USING gin (content gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_kb_chunks_content_trgm")
    op.drop_index('ix_kb_chunks_doc_id', table_name='kb_chunks')
    op.drop_index('ix_kb_chunks_kb_id', table_name='kb_chunks')
    op.drop_table('kb_chunks')
    # 扩展不在 downgrade 中删除，避免影响其他可能使用它的功能
