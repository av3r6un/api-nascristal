"""add index to properties

Revision ID: a5c2d9e7b341
Revises: 1d7e6c4b9a10
Create Date: 2026-04-06 16:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a5c2d9e7b341"
down_revision: Union[str, Sequence[str], None] = "1d7e6c4b9a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_table_names() -> set[str]:
  return set(sa.inspect(op.get_bind()).get_table_names())


def _get_column_names(table_name: str) -> set[str]:
  return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
  table_names = _get_table_names()
  if "properties" not in table_names:
    return

  column_names = _get_column_names("properties")
  if "index" in column_names:
    return

  with op.batch_alter_table("properties") as batch_op:
    batch_op.add_column(sa.Column("index", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
  table_names = _get_table_names()
  if "properties" not in table_names:
    return

  column_names = _get_column_names("properties")
  if "index" not in column_names:
    return

  with op.batch_alter_table("properties") as batch_op:
    batch_op.drop_column("index")
