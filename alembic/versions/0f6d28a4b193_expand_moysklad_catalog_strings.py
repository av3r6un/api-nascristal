"""Match catalog string lengths to the MoySklad API contract."""
from alembic import op
import sqlalchemy as sa


revision = '0f6d28a4b193'
down_revision = '7e4a9c2b1d60'
branch_labels = None
depends_on = None

LENGTHS = {
  'products': {'name': 50, 'code': 15, 'external_code': 24, 'sku': 25},
  'product_variants': {'name': 50, 'code': 15, 'external_code': 24, 'sku': 48},
}


def resize(upgrade):
  # SQLite does not enforce VARCHAR lengths; avoid rebuilding referenced tables.
  if op.get_context().dialect.name == 'sqlite':
    return
  for table, columns in LENGTHS.items():
    for column, length in columns.items():
      op.alter_column(table, column,
        existing_type=sa.String(length if upgrade else 255),
        type_=sa.String(255 if upgrade else length),
        existing_nullable=table == 'products' and column == 'sku',
      )


def upgrade():
  resize(True)


def downgrade():
  resize(False)
