"""Add saved integration configurations and site-owned delivery shipments."""
from alembic import op
import sqlalchemy as sa

revision = '2e8c6a4d9b10'
down_revision = '0f6d28a4b193'
branch_labels = None
depends_on = None


def timestamps():
  return [sa.Column('created', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    sa.Column('updated', sa.DateTime(), nullable=False, server_default=sa.func.now())]


def upgrade():
  op.create_table('integration_configs',
    sa.Column('code', sa.String(32), primary_key=True),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('config', sa.JSON(), nullable=False), *timestamps(),
    mysql_default_charset='utf8mb4', mysql_collate='utf8mb4_general_ci')
  op.create_table('delivery_shipments',
    sa.Column('id', sa.Integer(), primary_key=True),
    sa.Column('purchase_id', sa.Integer(), sa.ForeignKey('purchases.id'), nullable=False),
    sa.Column('provider', sa.String(32), nullable=False),
    sa.Column('environment', sa.String(16), nullable=False),
    sa.Column('account_fingerprint', sa.String(64), nullable=False),
    sa.Column('external_number', sa.String(40), nullable=False, unique=True),
    sa.Column('remote_uuid', sa.String(36), nullable=True, unique=True),
    sa.Column('tracking_number', sa.String(32), nullable=True),
    sa.Column('status', sa.String(32), nullable=False),
    sa.Column('request_payload', sa.JSON(), nullable=False),
    sa.Column('response_payload', sa.JSON(), nullable=False),
    sa.Column('operations', sa.JSON(), nullable=False), *timestamps(),
    sa.UniqueConstraint('purchase_id', name='uq_delivery_purchase'),
    mysql_default_charset='utf8mb4', mysql_collate='utf8mb4_general_ci')


def downgrade():
  op.drop_table('delivery_shipments')
  op.drop_table('integration_configs')
