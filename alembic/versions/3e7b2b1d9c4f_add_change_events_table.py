"""Add change events table

Revision ID: 3e7b2b1d9c4f
Revises: f7f9e6f1a2b3
Create Date: 2026-03-20 12:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3e7b2b1d9c4f'
down_revision: Union[str, Sequence[str], None] = 'f7f9e6f1a2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    'change_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('event_type', sa.String(length=100), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=True),
    sa.Column('actor_uid', sa.String(length=6), nullable=True),
    sa.Column('created', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column('updated', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
  )
  op.create_index(op.f('ix_change_events_event_type'), 'change_events', ['event_type'], unique=False)


def downgrade() -> None:
  op.drop_index(op.f('ix_change_events_event_type'), table_name='change_events')
  op.drop_table('change_events')
