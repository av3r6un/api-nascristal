"""add warehouse spec tables

Revision ID: 9c6f8e72b4ad
Revises: 3e7b2b1d9c4f, 8b7f9c1e4a2d
Create Date: 2026-03-24 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9c6f8e72b4ad"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "categories" not in table_names:
        op.create_table(
            "categories",
            sa.Column("uid", sa.String(length=8), nullable=False),
            sa.Column("index", sa.Integer(), nullable=False),
            sa.Column("icon", sa.String(length=25), server_default="diamond", nullable=False),
            sa.Column("created", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("uid"),
            mysql_default_charset="utf8mb4",
            mysql_collate="utf8mb4_general_ci",
        )

    if "category_translations" not in table_names:
        op.create_table(
            "category_translations",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("category_uid", sa.String(length=8), nullable=False),
            sa.Column("locale", sa.String(length=2), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["category_uid"], ["categories.uid"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("category_uid", "locale", name="uq_category_translations_category_locale"),
            mysql_default_charset="utf8mb4",
            mysql_collate="utf8mb4_general_ci",
        )

    if "colors" not in table_names:
        op.create_table(
            "colors",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("sku", sa.String(length=50), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("created", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("sku"),
            mysql_default_charset="utf8mb4",
            mysql_collate="utf8mb4_general_ci",
        )

    if "sizes" not in table_names:
        op.create_table(
            "sizes",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("sku", sa.String(length=50), nullable=False),
            sa.Column("size_min", sa.Integer(), nullable=False),
            sa.Column("size_max", sa.Integer(), nullable=False),
            sa.Column("created", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("sku"),
            mysql_default_charset="utf8mb4",
            mysql_collate="utf8mb4_general_ci",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "sizes" in table_names:
        op.drop_table("sizes")

    if "colors" in table_names:
        op.drop_table("colors")

    if "category_translations" in table_names:
        op.drop_table("category_translations")

    if "categories" in table_names:
        op.drop_table("categories")
