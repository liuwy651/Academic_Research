"""add_token_count_to_messages

Revision ID: b3f1c2d4e5a6
Revises: aef70e15984b
Create Date: 2026-04-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3f1c2d4e5a6'
down_revision: Union[str, None] = 'aef70e15984b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('messages', sa.Column('token_count', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('messages', 'token_count')
