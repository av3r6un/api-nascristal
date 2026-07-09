"""Decouple purchase payment fields

Revision ID: b7a2d4c9e8f1
Revises: 9c3e1f7a4b20
Create Date: 2026-07-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7a2d4c9e8f1"
down_revision: Union[str, Sequence[str], None] = "9c3e1f7a4b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  with op.batch_alter_table("purchases") as batch_op:
    batch_op.drop_column("payment_status")
    batch_op.drop_column("payment_method")


def downgrade() -> None:
  payment_status_enum = sa.Enum("PENDING", "PAID", "FAILED", name="paymentstatus")
  with op.batch_alter_table("purchases") as batch_op:
    batch_op.add_column(sa.Column("payment_method", sa.String(length=50), nullable=False, server_default="card"))
    batch_op.add_column(sa.Column("payment_status", payment_status_enum, nullable=False, server_default="PENDING"))
