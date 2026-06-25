"""Add payments and link purchases

Revision ID: 9c3e1f7a4b20
Revises: 6b2f4d9a8c10
Create Date: 2026-06-25 09:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9c3e1f7a4b20"
down_revision: Union[str, Sequence[str], None] = "6b2f4d9a8c10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    "payments",
    sa.Column("id", sa.Integer(), nullable=False),
    sa.Column("uuid", sa.String(length=36), nullable=False),
    sa.Column("provider", sa.String(length=32), nullable=False),
    sa.Column("idempotency_key", sa.String(length=64), nullable=False),
    sa.Column("external_payment_id", sa.String(length=64), nullable=True),
    sa.Column("status", sa.String(length=32), nullable=False),
    sa.Column("amount_value", sa.String(length=32), nullable=False),
    sa.Column("currency", sa.String(length=3), nullable=False),
    sa.Column("paid", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("confirmation_url", sa.String(length=2048), nullable=True),
    sa.Column("return_url", sa.String(length=2048), nullable=True),
    sa.Column("description", sa.String(length=255), nullable=True),
    sa.Column("metadata", sa.JSON(), nullable=False),
    sa.Column("request_payload", sa.JSON(), nullable=False),
    sa.Column("response_payload", sa.JSON(), nullable=False),
    sa.Column("notification_payload", sa.JSON(), nullable=False),
    sa.Column("created", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
    sa.Column("updated", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
    sa.PrimaryKeyConstraint("id"),
    mysql_collate="utf8mb4_general_ci",
    mysql_default_charset="utf8mb4",
  )
  op.create_index(op.f("ix_payments_uuid"), "payments", ["uuid"], unique=True)
  op.create_index(op.f("ix_payments_idempotency_key"), "payments", ["idempotency_key"], unique=True)
  op.create_index(op.f("ix_payments_external_payment_id"), "payments", ["external_payment_id"], unique=True)

  with op.batch_alter_table("purchases") as batch_op:
    batch_op.add_column(sa.Column("payment_id", sa.Integer(), nullable=True))
    batch_op.create_index(op.f("ix_purchases_payment_id"), ["payment_id"], unique=False)
    batch_op.create_foreign_key(
      "fk_purchases_payment_id_payments",
      "payments",
      ["payment_id"],
      ["id"],
    )


def downgrade() -> None:
  with op.batch_alter_table("purchases") as batch_op:
    batch_op.drop_constraint("fk_purchases_payment_id_payments", type_="foreignkey")
    batch_op.drop_index(op.f("ix_purchases_payment_id"))
    batch_op.drop_column("payment_id")

  op.drop_index(op.f("ix_payments_external_payment_id"), table_name="payments")
  op.drop_index(op.f("ix_payments_idempotency_key"), table_name="payments")
  op.drop_index(op.f("ix_payments_uuid"), table_name="payments")
  op.drop_table("payments")
