"""rename property_options and add metadata

Revision ID: 6a3d8f1c2b7e
Revises: e4b7c1d2a9f0
Create Date: 2026-03-30 18:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6a3d8f1c2b7e"
down_revision: Union[str, Sequence[str], None] = "e4b7c1d2a9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_table_names() -> set[str]:
  return set(sa.inspect(op.get_bind()).get_table_names())


def _get_column_names(table_name: str) -> set[str]:
  return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
  table_names = _get_table_names()
  if "propery_options" in table_names and "property_options" not in table_names:
    op.rename_table("propery_options", "property_options")
    table_names.remove("propery_options")
    table_names.add("property_options")

  if "property_options" not in table_names:
    return

  column_names = _get_column_names("property_options")
  with op.batch_alter_table("property_options") as batch_op:
    if "name" not in column_names:
      batch_op.add_column(sa.Column("name", sa.String(length=255), nullable=True))
    if "icon" not in column_names:
      batch_op.add_column(sa.Column("icon", sa.String(length=255), nullable=True))


def downgrade() -> None:
  table_names = _get_table_names()
  target_table = "property_options" if "property_options" in table_names else "propery_options"
  if target_table not in table_names:
    return

  column_names = _get_column_names(target_table)
  with op.batch_alter_table(target_table) as batch_op:
    if "icon" in column_names:
      batch_op.drop_column("icon")
    if "name" in column_names:
      batch_op.drop_column("name")

  table_names = _get_table_names()
  if "property_options" in table_names and "propery_options" not in table_names:
    op.rename_table("property_options", "propery_options")
