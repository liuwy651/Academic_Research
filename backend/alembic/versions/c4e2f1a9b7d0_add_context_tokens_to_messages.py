"""add_context_tokens_to_messages

Revision ID: c4e2f1a9b7d0
Revises: b3f1c2d4e5a6
Create Date: 2026-04-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4e2f1a9b7d0'
down_revision: Union[str, None] = 'b3f1c2d4e5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Stores the total prompt token count at this point in the conversation tree.
    # Only populated for assistant messages; NULL for user/system messages.
    op.add_column('messages', sa.Column('context_tokens', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('messages', 'context_tokens')
