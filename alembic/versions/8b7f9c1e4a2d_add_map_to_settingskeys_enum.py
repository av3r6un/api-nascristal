"""Add MAP to settings enum

Revision ID: 8b7f9c1e4a2d
Revises: f7f9e6f1a2b3
Create Date: 2026-03-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8b7f9c1e4a2d"
down_revision: Union[str, Sequence[str], None] = "f7f9e6f1a2b3"
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
                'MAINTENANCE'
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
                'SEO',
                'MAINTENANCE'
            ) NOT NULL
            """
        )
    )
