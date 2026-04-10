"""repair missing model tables

Revision ID: d4f8a1b2c3e9
Revises: c9f1e4a2d8b6
Create Date: 2026-04-10 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4f8a1b2c3e9"
down_revision: Union[str, Sequence[str], None] = "c9f1e4a2d8b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _create_onec_import_runs() -> None:
    op.create_table(
        "onec_import_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("exchange_type", sa.String(length=32), nullable=False),
        sa.Column("classifier_id", sa.String(length=36), nullable=True),
        sa.Column("source_md5", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_default_charset="utf8mb4",
        mysql_collate="utf8mb4_general_ci",
    )
    op.create_index("ix_onec_import_runs_source_md5", "onec_import_runs", ["source_md5"], unique=False)


def _create_products() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("eid", sa.String(length=36), nullable=False),
        sa.Column("sku", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("primary_image", sa.String(length=512), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("last_seen_import_run_id", sa.Integer(), nullable=True),
        sa.Column("created", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["last_seen_import_run_id"], ["onec_import_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("eid"),
        sa.UniqueConstraint("sku"),
        sa.UniqueConstraint("code"),
        mysql_default_charset="utf8mb4",
        mysql_collate="utf8mb4_general_ci",
    )
    op.create_index("ix_products_eid", "products", ["eid"], unique=False)
    op.create_index("ix_products_category_id", "products", ["category_id"], unique=False)
    op.create_index("ix_products_last_seen_import_run_id", "products", ["last_seen_import_run_id"], unique=False)


def _create_product_images() -> None:
    op.create_table(
        "product_images",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("eid", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("created", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("eid"),
        sa.UniqueConstraint("product_id", "path", name="uq_product_images_product_path"),
        mysql_default_charset="utf8mb4",
        mysql_collate="utf8mb4_general_ci",
    )
    op.create_index("ix_product_images_eid", "product_images", ["eid"], unique=False)
    op.create_index("ix_product_images_product_id", "product_images", ["product_id"], unique=False)


def _create_product_attributes() -> None:
    op.create_table(
        "product_attributes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("eid", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("property_id", sa.Integer(), nullable=False),
        sa.Column("option_id", sa.Integer(), nullable=True),
        sa.Column("created", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
        sa.ForeignKeyConstraint(["option_id"], ["property_options.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("eid"),
        sa.UniqueConstraint("product_id", "property_id", name="uq_product_attributes_product_property"),
        mysql_default_charset="utf8mb4",
        mysql_collate="utf8mb4_general_ci",
    )
    op.create_index("ix_product_attributes_eid", "product_attributes", ["eid"], unique=False)
    op.create_index("ix_product_attributes_product_id", "product_attributes", ["product_id"], unique=False)
    op.create_index("ix_product_attributes_property_id", "product_attributes", ["property_id"], unique=False)
    op.create_index("ix_product_attributes_option_id", "product_attributes", ["option_id"], unique=False)


def _create_offers() -> None:
    op.create_table(
        "offers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("eid", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), server_default="0", nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=True),
        sa.Column("coefficient", sa.Numeric(18, 4), server_default="1", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), server_default="0", nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=True),
        sa.Column("created", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("eid"),
        sa.UniqueConstraint("product_id", name="uq_offers_product_id"),
        mysql_default_charset="utf8mb4",
        mysql_collate="utf8mb4_general_ci",
    )
    op.create_index("ix_offers_eid", "offers", ["eid"], unique=False)
    op.create_index("ix_offers_product_id", "offers", ["product_id"], unique=False)


def upgrade() -> None:
    table_names = _table_names()

    if "onec_import_runs" not in table_names:
        _create_onec_import_runs()

    table_names = _table_names()
    if "products" not in table_names:
        _create_products()

    table_names = _table_names()
    if "product_images" not in table_names:
        _create_product_images()
    if "product_attributes" not in table_names:
        _create_product_attributes()
    if "offers" not in table_names:
        _create_offers()


def downgrade() -> None:
    table_names = _table_names()

    if "offers" in table_names:
        op.drop_table("offers")
    if "product_attributes" in table_names:
        op.drop_table("product_attributes")
    if "product_images" in table_names:
        op.drop_table("product_images")
    if "products" in table_names:
        op.drop_table("products")
    if "onec_import_runs" in table_names:
        op.drop_table("onec_import_runs")
