"""Add purchases

Revision ID: 6b2f4d9a8c10
Revises: d4f8a1b2c3e9
Create Date: 2026-05-28 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6b2f4d9a8c10'
down_revision: Union[str, Sequence[str], None] = 'd4f8a1b2c3e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    'purchases',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('uuid', sa.String(length=36), nullable=False),
    sa.Column('product_ids', sa.JSON(), nullable=False),
    sa.Column('properties', sa.JSON(), nullable=False),
    sa.Column('product_quantities', sa.JSON(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('contact_info', sa.JSON(), nullable=False),
    sa.Column('final_price', sa.Integer(), nullable=False),
    sa.Column('payment_method', sa.String(length=50), nullable=False),
    sa.Column('payment_status', sa.Enum('PENDING', 'PAID', 'FAILED', name='paymentstatus'), server_default='PENDING', nullable=False),
    sa.Column('status', sa.Enum('CREATED', 'PROCESSING', 'DELIVERING', 'FINISHED', name='purchasestatus'), server_default='CREATED', nullable=False),
    sa.Column('created', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    mysql_collate='utf8mb4_general_ci',
    mysql_default_charset='utf8mb4',
  )
  op.create_index(op.f('ix_purchases_uuid'), 'purchases', ['uuid'], unique=True)


def downgrade() -> None:
  op.drop_index(op.f('ix_purchases_uuid'), table_name='purchases')
  op.drop_table('purchases')
