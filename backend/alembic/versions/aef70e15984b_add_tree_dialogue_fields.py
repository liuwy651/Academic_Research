"""add_tree_dialogue_fields

Revision ID: aef70e15984b
Revises: d93ff7120aaf
Create Date: 2026-04-24 18:47:43.733646

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'aef70e15984b'
down_revision: Union[str, None] = 'd93ff7120aaf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('messages', sa.Column('parent_id', sa.Uuid(), nullable=True))
    op.add_column('messages', sa.Column('summary', sa.String(length=20), nullable=True))
    op.create_index(op.f('ix_messages_parent_id'), 'messages', ['parent_id'], unique=False)
    op.create_foreign_key(
        'fk_messages_parent_id', 'messages', 'messages', ['parent_id'], ['id'], ondelete='SET NULL'
    )
    op.add_column('conversations', sa.Column('current_node_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(
        'fk_conversations_current_node_id', 'conversations', 'messages',
        ['current_node_id'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('fk_conversations_current_node_id', 'conversations', type_='foreignkey')
    op.drop_column('conversations', 'current_node_id')
    op.drop_constraint('fk_messages_parent_id', 'messages', type_='foreignkey')
    op.drop_index(op.f('ix_messages_parent_id'), table_name='messages')
    op.drop_column('messages', 'summary')
    op.drop_column('messages', 'parent_id')
