"""Replace legacy catalog tables with MoySklad catalog tables.

Revision ID: 59ca8b5b7134
Revises: 1f2a3b4c5d6e
Create Date: 2026-08-22 17:05:33.309292

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "59ca8b5b7134"
down_revision: Union[str, Sequence[str], None] = "1f2a3b4c5d6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


MYSQL_TABLE_ARGS = {
  "mysql_default_charset": "utf8mb4",
  "mysql_collate": "utf8mb4_general_ci",
}


def _table_names() -> set[str]:
  return set(sa.inspect(op.get_bind()).get_table_names())


def _drop_if_exists(table_name: str) -> None:
  if table_name in _table_names():
    op.drop_table(table_name)


def _create_categories() -> None:
  op.create_table(
    "categories",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("name", sa.String(length=50), nullable=False),
    sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
    sa.Column("created", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column("updated", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint("id"),
    **MYSQL_TABLE_ARGS,
  )


def _create_products() -> None:
  op.create_table(
    "products",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.Uuid(), nullable=False),
    sa.Column("sku", sa.String(length=25), nullable=True),
    sa.Column("name", sa.String(length=50), nullable=False),
    sa.Column("description", sa.Text(), nullable=True),
    sa.Column("code", sa.String(length=15), nullable=False),
    sa.Column("external_code", sa.String(length=24), nullable=False),
    sa.Column("category_id", sa.Integer(), nullable=False),
    sa.Column("server_updated", sa.DateTime(), nullable=False),
    sa.Column("archived", sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column("created", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column("updated", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("code"),
    sa.UniqueConstraint("uuid"),
    **MYSQL_TABLE_ARGS,
  )


def _create_product_variants() -> None:
  op.create_table(
    "product_variants",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.Uuid(), nullable=False),
    sa.Column("product_id", sa.Integer(), nullable=False),
    sa.Column("name", sa.String(length=50), nullable=False),
    sa.Column("code", sa.String(length=15), nullable=False),
    sa.Column("external_code", sa.String(length=24), nullable=False),
    sa.Column("archived", sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column("sku", sa.String(length=48), nullable=False),
    sa.Column("image_key", sa.String(length=255), nullable=True),
    sa.Column("created", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column("updated", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("code"),
    sa.UniqueConstraint("uuid"),
    **MYSQL_TABLE_ARGS,
  )


def _create_attributes() -> None:
  op.create_table(
    "attributes",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.Uuid(), nullable=False),
    sa.Column("name", sa.String(length=25), nullable=False),
    sa.Column("created", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column("updated", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("uuid"),
    **MYSQL_TABLE_ARGS,
  )


def _create_attribute_options() -> None:
  op.create_table(
    "attribute_options",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("attribute_id", sa.Integer(), nullable=False),
    sa.Column("value", sa.String(length=255), nullable=False),
    sa.Column("label", sa.String(length=255), nullable=True),
    sa.Column("created", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column("updated", sa.DateTime(), server_default=sa.func.now(), nullable=False),
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
    sa.Column("created", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column("updated", sa.DateTime(), server_default=sa.func.now(), nullable=False),
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


def _create_product_images() -> None:
  op.create_table(
    "product_images",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.Uuid(), nullable=False),
    sa.Column("product_id", sa.Integer(), nullable=False),
    sa.Column("object_key", sa.String(length=255), nullable=False),
    sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
    sa.Column("is_primary", sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column("created", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column("updated", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint(
      "product_id",
      "object_key",
      name="uq_product_images_product_object_key",
    ),
    sa.UniqueConstraint("uuid"),
    **MYSQL_TABLE_ARGS,
  )
  op.create_index(
    op.f("ix_product_images_product_id"),
    "product_images",
    ["product_id"],
    unique=False,
  )


def _create_offers() -> None:
  op.create_table(
    "offers",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("variant_id", sa.Integer(), nullable=False),
    sa.Column("amount", sa.DECIMAL(precision=12, scale=2), server_default="0.00", nullable=False),
    sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.Column("quantity", sa.Double(), server_default="0", nullable=False),
    sa.Column("created", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column("updated", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"]),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("variant_id", name="uq_offers_variant_id"),
    **MYSQL_TABLE_ARGS,
  )
  op.create_index(
    op.f("ix_offers_variant_id"),
    "offers",
    ["variant_id"],
    unique=False,
  )


def _create_legacy_categories() -> None:
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
    **MYSQL_TABLE_ARGS,
  )
  op.create_index("ix_categories_eid", "categories", ["eid"], unique=False)


def _create_legacy_import_runs() -> None:
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
    **MYSQL_TABLE_ARGS,
  )
  op.create_index(
    "ix_onec_import_runs_source_md5",
    "onec_import_runs",
    ["source_md5"],
    unique=False,
  )


def _create_legacy_properties() -> None:
  op.create_table(
    "properties",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("eid", sa.String(length=36), nullable=False),
    sa.Column("parent_category_id", sa.Integer(), nullable=True),
    sa.Column("index", sa.Integer(), server_default="0", nullable=False),
    sa.Column("name", sa.String(length=255), nullable=False),
    sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
    sa.Column("created", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column("updated", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(
      ["parent_category_id"],
      ["categories.id"],
      name="fk_properties_parent_category_id_categories",
    ),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("eid"),
    **MYSQL_TABLE_ARGS,
  )
  op.create_index("ix_properties_eid", "properties", ["eid"], unique=False)
  op.create_index(
    "ix_properties_parent_category_id",
    "properties",
    ["parent_category_id"],
    unique=False,
  )


def _create_legacy_property_options() -> None:
  op.create_table(
    "property_options",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("eid", sa.String(length=36), nullable=False),
    sa.Column("property_id", sa.Integer(), nullable=False),
    sa.Column("value", sa.String(length=255), nullable=False),
    sa.Column("name", sa.String(length=255), nullable=True),
    sa.Column("icon", sa.String(length=255), nullable=True),
    sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
    sa.Column("created", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column("updated", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("eid"),
    sa.UniqueConstraint(
      "property_id",
      "value",
      name="uq_property_options_property_value",
    ),
    **MYSQL_TABLE_ARGS,
  )
  op.create_index("ix_property_options_eid", "property_options", ["eid"], unique=False)
  op.create_index(
    "ix_property_options_property_id",
    "property_options",
    ["property_id"],
    unique=False,
  )


def _create_legacy_products() -> None:
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
    sa.UniqueConstraint("code"),
    sa.UniqueConstraint("eid"),
    sa.UniqueConstraint("sku"),
    **MYSQL_TABLE_ARGS,
  )
  op.create_index("ix_products_category_id", "products", ["category_id"], unique=False)
  op.create_index("ix_products_eid", "products", ["eid"], unique=False)
  op.create_index(
    "ix_products_last_seen_import_run_id",
    "products",
    ["last_seen_import_run_id"],
    unique=False,
  )


def _create_legacy_product_images() -> None:
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
    sa.UniqueConstraint(
      "product_id",
      "path",
      name="uq_product_images_product_path",
    ),
    **MYSQL_TABLE_ARGS,
  )
  op.create_index("ix_product_images_eid", "product_images", ["eid"], unique=False)
  op.create_index(
    "ix_product_images_product_id",
    "product_images",
    ["product_id"],
    unique=False,
  )


def _create_legacy_product_attributes() -> None:
  op.create_table(
    "product_attributes",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("eid", sa.String(length=36), nullable=False),
    sa.Column("product_id", sa.Integer(), nullable=False),
    sa.Column("property_id", sa.Integer(), nullable=False),
    sa.Column("option_id", sa.Integer(), nullable=True),
    sa.Column("created", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column("updated", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(["option_id"], ["property_options.id"]),
    sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
    sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("eid"),
    sa.UniqueConstraint(
      "product_id",
      "property_id",
      name="uq_product_attributes_product_property",
    ),
    **MYSQL_TABLE_ARGS,
  )
  op.create_index("ix_product_attributes_eid", "product_attributes", ["eid"], unique=False)
  op.create_index(
    "ix_product_attributes_option_id",
    "product_attributes",
    ["option_id"],
    unique=False,
  )
  op.create_index(
    "ix_product_attributes_product_id",
    "product_attributes",
    ["product_id"],
    unique=False,
  )
  op.create_index(
    "ix_product_attributes_property_id",
    "product_attributes",
    ["property_id"],
    unique=False,
  )


def _create_legacy_offers() -> None:
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
    **MYSQL_TABLE_ARGS,
  )
  op.create_index("ix_offers_eid", "offers", ["eid"], unique=False)
  op.create_index("ix_offers_product_id", "offers", ["product_id"], unique=False)


def _create_purchase_submissions() -> None:
  op.create_table(
    "purchase_submissions",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("uuid", sa.Uuid(), nullable=False),
    sa.Column("order_id", sa.String(length=255), nullable=False),
    sa.Column("purchase_id", sa.Integer(), nullable=False),
    sa.Column("created", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column("updated", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(["purchase_id"], ["purchases.id"]),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("uuid", name="uq_purchase_submissions_uuid"),
    sa.UniqueConstraint("order_id", name="uq_purchase_submissions_order_id"),
    sa.UniqueConstraint("purchase_id", name="uq_purchase_submissions_purchase_id"),
    **MYSQL_TABLE_ARGS,
  )


def upgrade() -> None:
  # Replacing the catalog is intentional. No legacy catalog rows are copied.
  for table_name in (
    "offers",
    "product_attributes",
    "attribute_options",
    "product_images",
    "product_variants",
    "products",
    "property_options",
    "propery_options",
    "properties",
    "onec_import_runs",
    "categories",
  ):
    _drop_if_exists(table_name)

  _create_categories()
  _create_products()
  _create_product_variants()
  _create_attributes()
  _create_attribute_options()
  _create_product_attributes()
  _create_product_images()
  _create_offers()
  _create_purchase_submissions()


def downgrade() -> None:
  for table_name in (
    "offers",
    "product_attributes",
    "attribute_options",
    "product_images",
    "attributes",
    "product_variants",
    "products",
    "categories",
    "purchase_submissions",
  ):
    _drop_if_exists(table_name)

  _create_legacy_categories()
  _create_legacy_import_runs()
  _create_legacy_properties()
  _create_legacy_property_options()
  _create_legacy_products()
  _create_legacy_product_images()
  _create_legacy_product_attributes()
  _create_legacy_offers()
