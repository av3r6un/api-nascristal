"""add parent category to properties

Revision ID: 1d7e6c4b9a10
Revises: 6a3d8f1c2b7e
Create Date: 2026-04-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1d7e6c4b9a10"
down_revision: Union[str, Sequence[str], None] = "6a3d8f1c2b7e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_table_names() -> set[str]:
  return set(sa.inspect(op.get_bind()).get_table_names())


def _get_column_names(table_name: str) -> set[str]:
  return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _get_foreign_keys(table_name: str) -> set[str]:
  return {foreign_key["name"] for foreign_key in sa.inspect(op.get_bind()).get_foreign_keys(table_name) if foreign_key.get("name")}


def _get_indexes(table_name: str) -> set[str]:
  return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def upgrade() -> None:
  table_names = _get_table_names()
  if "properties" not in table_names:
    return

  column_names = _get_column_names("properties")
  foreign_keys = _get_foreign_keys("properties")
  indexes = _get_indexes("properties")

  with op.batch_alter_table("properties") as batch_op:
    if "parent_category_id" not in column_names:
      batch_op.add_column(sa.Column("parent_category_id", sa.Integer(), nullable=True))
    if "fk_properties_parent_category_id_categories" not in foreign_keys:
      batch_op.create_foreign_key(
        "fk_properties_parent_category_id_categories",
        "categories",
        ["parent_category_id"],
        ["id"],
      )
    if "ix_properties_parent_category_id" not in indexes:
      batch_op.create_index("ix_properties_parent_category_id", ["parent_category_id"], unique=False)


def downgrade() -> None:
  table_names = _get_table_names()
  if "properties" not in table_names:
    return

  column_names = _get_column_names("properties")
  foreign_keys = _get_foreign_keys("properties")
  indexes = _get_indexes("properties")

  with op.batch_alter_table("properties") as batch_op:
    if "ix_properties_parent_category_id" in indexes:
      batch_op.drop_index("ix_properties_parent_category_id")
    if "fk_properties_parent_category_id_categories" in foreign_keys:
      batch_op.drop_constraint("fk_properties_parent_category_id_categories", type_="foreignkey")
    if "parent_category_id" in column_names:
      batch_op.drop_column("parent_category_id")
