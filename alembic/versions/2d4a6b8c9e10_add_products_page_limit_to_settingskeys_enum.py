"""Add PRODUCTS_PAGE_LIMIT to settings enum

Revision ID: 2d4a6b8c9e10
Revises: 1d7e6c4b9a10
Create Date: 2026-04-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2d4a6b8c9e10"
down_revision: Union[str, Sequence[str], None] = "1d7e6c4b9a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "settings" not in inspector.get_table_names():
        return

    if bind.dialect.name != "mysql":
        return

    op.execute(
        sa.text(
            """
            ALTER TABLE settings
            MODIFY COLUMN `key` ENUM(
                'SITE_NAME',
                'LOGO_URL',
                'SOCIALS',
                'CONTACTS',
                'MAP',
                'SEO',
                'MAINTENANCE',
                'PRODUCTS_PAGE_LIMIT'
            ) NOT NULL
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "settings" not in inspector.get_table_names():
        return

    if bind.dialect.name != "mysql":
        return

    op.execute(
        sa.text(
            """
            ALTER TABLE settings
            MODIFY COLUMN `key` ENUM(
                'SITE_NAME',
                'LOGO_URL',
                'SOCIALS',
                'CONTACTS',
                'MAP',
                'SEO',
                'MAINTENANCE'
            ) NOT NULL
            """
        )
    )
