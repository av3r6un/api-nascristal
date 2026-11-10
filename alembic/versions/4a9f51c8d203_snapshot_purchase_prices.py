"""Store order totals with kopecks and snapshot line prices."""
import sqlalchemy as sa
from alembic import op

revision = '4a9f51c8d203'
down_revision = '3b7d2a61ce94'
branch_labels = None
depends_on = None


def upgrade():
  with op.batch_alter_table('purchases') as batch:
    batch.alter_column('final_price', existing_type=sa.Integer(), type_=sa.Numeric(14, 2), existing_nullable=False)
    batch.add_column(sa.Column('price_snapshot', sa.JSON(), nullable=True))


def downgrade():
  purchases = sa.table('purchases', sa.column('final_price'))
  if op.get_bind().execute(sa.select(purchases.c.final_price).where(
    purchases.c.final_price != sa.func.floor(purchases.c.final_price)
  ).limit(1)).first():
    raise RuntimeError('Cannot downgrade purchases with fractional totals')
  with op.batch_alter_table('purchases') as batch:
    batch.drop_column('price_snapshot')
    batch.alter_column('final_price', existing_type=sa.Numeric(14, 2), type_=sa.Integer(), existing_nullable=False)
