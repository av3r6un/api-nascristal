"""Add awaiting payment purchase status

Revision ID: 1f2a3b4c5d6e
Revises: b7a2d4c9e8f1
Create Date: 2026-07-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "1f2a3b4c5d6e"
down_revision: Union[str, Sequence[str], None] = "b7a2d4c9e8f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_STATUSES = ("CREATED", "AWAITING_PAYMENT", "PROCESSING", "DELIVERING", "FINISHED")
OLD_STATUSES = ("CREATED", "PROCESSING", "DELIVERING", "FINISHED")


def _mysql_enum_values(values: tuple[str, ...]) -> str:
  return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
  bind = op.get_bind()
  dialect = bind.dialect.name

  if dialect == "mysql":
    op.execute(
      f"ALTER TABLE purchases MODIFY status ENUM({_mysql_enum_values(NEW_STATUSES)}) "
      "NOT NULL DEFAULT 'CREATED'"
    )
  elif dialect == "postgresql":
    with op.get_context().autocommit_block():
      op.execute("ALTER TYPE purchasestatus ADD VALUE IF NOT EXISTS 'AWAITING_PAYMENT'")

  op.execute("UPDATE purchases SET status = 'AWAITING_PAYMENT' WHERE status = 'PROCESSING'")


def downgrade() -> None:
  bind = op.get_bind()
  dialect = bind.dialect.name

  op.execute("UPDATE purchases SET status = 'PROCESSING' WHERE status = 'AWAITING_PAYMENT'")

  if dialect == "mysql":
    op.execute(
      f"ALTER TABLE purchases MODIFY status ENUM({_mysql_enum_values(OLD_STATUSES)}) "
      "NOT NULL DEFAULT 'CREATED'"
    )
  elif dialect == "postgresql":
    op.execute("ALTER TABLE purchases ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TYPE purchasestatus RENAME TO purchasestatus_old")
    op.execute("CREATE TYPE purchasestatus AS ENUM ('CREATED', 'PROCESSING', 'DELIVERING', 'FINISHED')")
    op.execute(
      "ALTER TABLE purchases ALTER COLUMN status TYPE purchasestatus "
      "USING status::text::purchasestatus"
    )
    op.execute("ALTER TABLE purchases ALTER COLUMN status SET DEFAULT 'CREATED'")
    op.execute("DROP TYPE purchasestatus_old")
