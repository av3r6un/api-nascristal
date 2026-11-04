"""Add the assembling stage between payment and delivery."""
from alembic import op
import sqlalchemy as sa

revision = '6c28d90ea413'
down_revision = '4b91c7d8e205'
branch_labels = None
depends_on = None

OLD = ('CREATED', 'AWAITING_PAYMENT', 'PROCESSING', 'DELIVERING', 'FINISHED')
NEW = (*OLD[:3], 'ASSEMBLING', *OLD[3:])


def upgrade():
  # SQLite stores this non-native enum as VARCHAR(16), already large enough.
  if op.get_bind().dialect.name == 'mysql':
    op.alter_column('purchases', 'status', existing_type=sa.Enum(*OLD, name='purchasestatus'),
      type_=sa.Enum(*NEW, name='purchasestatus'), existing_nullable=False,
      existing_server_default='CREATED')


def downgrade():
  op.execute("UPDATE purchases SET status = 'PROCESSING' WHERE status = 'ASSEMBLING'")
  if op.get_bind().dialect.name == 'mysql':
    op.alter_column('purchases', 'status', existing_type=sa.Enum(*NEW, name='purchasestatus'),
      type_=sa.Enum(*OLD, name='purchasestatus'), existing_nullable=False,
      existing_server_default='CREATED')
