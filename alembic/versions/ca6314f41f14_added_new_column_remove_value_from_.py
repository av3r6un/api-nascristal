"""Add normalized attribute options.

Revision ID: ca6314f41f14
Revises: 59ca8b5b7134
Create Date: 2026-08-24 18:26:49.771621
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ca6314f41f14"
down_revision: Union[str, Sequence[str], None] = "59ca8b5b7134"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


MYSQL_TABLE_ARGS = {
  "mysql_default_charset": "utf8mb4",
  "mysql_collate": "utf8mb4_general_ci",
}


def _create_attribute_options() -> None:
  op.create_table(
    "attribute_options",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("attribute_id", sa.Integer(), nullable=False),
    sa.Column("value", sa.String(length=255), nullable=False),
    sa.Column("label", sa.String(length=255), nullable=True),
    sa.Column("created", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    sa.Column("updated", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    sa.ForeignKeyConstraint(["attribute_id"], ["attributes.id"]),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint(
      "attribute_id",
      "value",
      name="uq_attribute_options_attribute_value",
    ),
    **MYSQL_TABLE_ARGS,
  )


def _create_product_attributes() -> None:
  op.create_table(
    "product_attributes",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("variant_id", sa.Integer(), nullable=False),
    sa.Column("option_id", sa.Integer(), nullable=False),
    sa.Column("created", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    sa.Column("updated", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    sa.ForeignKeyConstraint(["option_id"], ["attribute_options.id"]),
    sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"]),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint(
      "variant_id",
      "option_id",
      name="uq_product_attributes_variant_option",
    ),
    **MYSQL_TABLE_ARGS,
  )


def _create_old_product_attributes() -> None:
  op.create_table(
    "product_attributes",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("variant_id", sa.Integer(), nullable=False),
    sa.Column("attribute_id", sa.Integer(), nullable=False),
    sa.Column("value", sa.String(length=100), nullable=False),
    sa.Column("label", sa.String(length=100), nullable=True),
    sa.Column("created", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    sa.Column("updated", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    sa.ForeignKeyConstraint(["attribute_id"], ["attributes.id"]),
    sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"]),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint(
      "variant_id",
      "attribute_id",
      name="uq_product_attributes_variant_attribute",
    ),
    **MYSQL_TABLE_ARGS,
  )


def upgrade() -> None:
  op.drop_table("product_attributes")
  _create_attribute_options()
  _create_product_attributes()


def downgrade() -> None:
  op.drop_table("product_attributes")
  op.drop_table("attribute_options")
  _create_old_product_attributes()
