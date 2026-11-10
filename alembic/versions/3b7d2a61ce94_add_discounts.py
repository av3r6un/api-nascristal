"""Add MoySklad discounts and their assortment scope."""

import sqlalchemy as sa
from alembic import op


revision = '3b7d2a61ce94'
down_revision = '6c28d90ea413'
branch_labels = None
depends_on = None


def upgrade():
  op.create_table(
    'discounts',
    sa.Column('id', sa.Integer(), primary_key=True),
    sa.Column('uuid', sa.Uuid(), nullable=False, unique=True),
    sa.Column('name', sa.String(255), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('all_products', sa.Boolean(), nullable=False),
    sa.Column('amount', sa.Numeric(9, 6), nullable=False),
    sa.Column('created', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    sa.Column('updated', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    mysql_default_charset='utf8mb4',
    mysql_collate='utf8mb4_general_ci',
  )
  op.create_table(
    'discount_products',
    sa.Column('id', sa.Integer(), primary_key=True),
    sa.Column('discount_id', sa.Integer(), sa.ForeignKey('discounts.id', ondelete='CASCADE'), nullable=False),
    sa.Column('entity_type', sa.String(32), nullable=False),
    sa.Column('entity_uuid', sa.Uuid(), nullable=False),
    sa.Column('created', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    sa.Column('updated', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    sa.UniqueConstraint('discount_id', 'entity_type', 'entity_uuid', name='uq_discount_products_scope'),
    mysql_default_charset='utf8mb4',
    mysql_collate='utf8mb4_general_ci',
  )
  op.create_index('ix_discount_products_entity', 'discount_products', ['entity_type', 'entity_uuid'])


def downgrade():
  op.drop_table('discount_products')
  op.drop_table('discounts')
