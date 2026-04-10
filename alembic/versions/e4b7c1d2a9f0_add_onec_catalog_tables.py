"""add onec catalog tables

Revision ID: e4b7c1d2a9f0
Revises: 3e7b2b1d9c4f, 8b7f9c1e4a2d
Create Date: 2026-03-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e4b7c1d2a9f0"
down_revision: Union[str, Sequence[str], None] = ("3e7b2b1d9c4f", "8b7f9c1e4a2d")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_categories_table() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("eid", sa.String(length=36), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=255), server_default="", nullable=False),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("icon", sa.String(length=25), server_default="diamond", nullable=False),
        sa.Column("created", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["categories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("eid"),
        mysql_default_charset="utf8mb4",
        mysql_collate="utf8mb4_general_ci",
    )
    op.create_index("ix_categories_eid", "categories", ["eid"], unique=False)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "category_translations" in table_names:
        op.drop_table("category_translations")
        table_names.remove("category_translations")

    if "categories" in table_names:
        op.drop_table("categories")
        table_names.remove("categories")

    _create_categories_table()

    if "onec_import_runs" not in table_names:
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

    if "properties" not in table_names:
        op.create_table(
            "properties",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("eid", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
            sa.Column("created", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("eid"),
            mysql_default_charset="utf8mb4",
            mysql_collate="utf8mb4_general_ci",
        )
        op.create_index("ix_properties_eid", "properties", ["eid"], unique=False)

    if "propery_options" not in table_names:
        op.create_table(
            "propery_options",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("eid", sa.String(length=36), nullable=False),
            sa.Column("property_id", sa.Integer(), nullable=False),
            sa.Column("value", sa.String(length=255), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
            sa.Column("created", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("eid"),
            sa.UniqueConstraint("property_id", "value", name="uq_propery_options_property_value"),
            mysql_default_charset="utf8mb4",
            mysql_collate="utf8mb4_general_ci",
        )
        op.create_index("ix_propery_options_eid", "propery_options", ["eid"], unique=False)
        op.create_index("ix_propery_options_property_id", "propery_options", ["property_id"], unique=False)

    if "products" not in table_names:
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
            sa.UniqueConstraint("code"),
            sa.UniqueConstraint("sku"),
            mysql_default_charset="utf8mb4",
            mysql_collate="utf8mb4_general_ci",
        )
        op.create_index("ix_products_eid", "products", ["eid"], unique=False)
        op.create_index("ix_products_category_id", "products", ["category_id"], unique=False)
        op.create_index("ix_products_last_seen_import_run_id", "products", ["last_seen_import_run_id"], unique=False)

    if "product_images" not in table_names:
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

    if "product_attributes" not in table_names:
        op.create_table(
            "product_attributes",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("eid", sa.String(length=36), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("property_id", sa.Integer(), nullable=False),
            sa.Column("option_id", sa.Integer(), nullable=True),
            sa.Column("created", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["option_id"], ["propery_options.id"]),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
            sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("eid"),
            sa.UniqueConstraint("product_id", "property_id", name="uq_product_attributes_product_property"),
            mysql_default_charset="utf8mb4",
            mysql_collate="utf8mb4_general_ci",
        )
        op.create_index("ix_product_attributes_eid", "product_attributes", ["eid"], unique=False)
        op.create_index("ix_product_attributes_option_id", "product_attributes", ["option_id"], unique=False)
        op.create_index("ix_product_attributes_product_id", "product_attributes", ["product_id"], unique=False)
        op.create_index("ix_product_attributes_property_id", "product_attributes", ["property_id"], unique=False)

    if "offers" not in table_names:
        op.create_table(
            "offers",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("eid", sa.String(length=36), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("quantity", sa.Numeric(precision=18, scale=4), server_default="0", nullable=False),
            sa.Column("unit", sa.String(length=64), nullable=True),
            sa.Column("coefficient", sa.Numeric(precision=18, scale=4), server_default="1", nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
            sa.Column("amount", sa.Numeric(precision=18, scale=4), server_default="0", nullable=False),
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


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "offers" in table_names:
        op.drop_index("ix_offers_product_id", table_name="offers")
        op.drop_index("ix_offers_eid", table_name="offers")
        op.drop_table("offers")

    if "product_attributes" in table_names:
        op.drop_index("ix_product_attributes_property_id", table_name="product_attributes")
        op.drop_index("ix_product_attributes_product_id", table_name="product_attributes")
        op.drop_index("ix_product_attributes_option_id", table_name="product_attributes")
        op.drop_index("ix_product_attributes_eid", table_name="product_attributes")
        op.drop_table("product_attributes")

    if "product_images" in table_names:
        op.drop_index("ix_product_images_product_id", table_name="product_images")
        op.drop_index("ix_product_images_eid", table_name="product_images")
        op.drop_table("product_images")

    if "products" in table_names:
        op.drop_index("ix_products_last_seen_import_run_id", table_name="products")
        op.drop_index("ix_products_category_id", table_name="products")
        op.drop_index("ix_products_eid", table_name="products")
        op.drop_table("products")

    if "propery_options" in table_names:
        op.drop_index("ix_propery_options_property_id", table_name="propery_options")
        op.drop_index("ix_propery_options_eid", table_name="propery_options")
        op.drop_table("propery_options")

    if "properties" in table_names:
        op.drop_index("ix_properties_eid", table_name="properties")
        op.drop_table("properties")

    if "onec_import_runs" in table_names:
        op.drop_index("ix_onec_import_runs_source_md5", table_name="onec_import_runs")
        op.drop_table("onec_import_runs")

    if "categories" in table_names:
        op.drop_index("ix_categories_eid", table_name="categories")
        op.drop_table("categories")
