"""create settings table

Revision ID: f7f9e6f1a2b3
Revises: 4127d08610dd
Create Date: 2026-03-05 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f7f9e6f1a2b3"
down_revision: Union[str, Sequence[str], None] = "4127d08610dd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "settings" in inspector.get_table_names():
        return

    op.create_table(
        "settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "key",
            sa.Enum(
                "SITE_NAME",
                "LOGO_URL",
                "SOCIALS",
                "CONTACTS",
                "SEO",
                "MAINTENANCE",
                name="settingskeys",
            ),
            nullable=False,
        ),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("created", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_default_charset="utf8mb4",
        mysql_collate="utf8mb4_general_ci",
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "settings" in inspector.get_table_names():
        op.drop_table("settings")
