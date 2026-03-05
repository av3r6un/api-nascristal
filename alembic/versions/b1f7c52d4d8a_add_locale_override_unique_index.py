"""add locale override unique index

Revision ID: b1f7c52d4d8a
Revises: cc400eadf331
Create Date: 2026-02-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1f7c52d4d8a"
down_revision: Union[str, Sequence[str], None] = "cc400eadf331"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "locale_overrides" not in inspector.get_table_names():
        return

    index_names = {idx["name"] for idx in inspector.get_indexes("locale_overrides")}
    if "uq_locale_overrides_locale_key" not in index_names:
        op.create_index(
            "uq_locale_overrides_locale_key",
            "locale_overrides",
            ["locale", "key"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "locale_overrides" not in inspector.get_table_names():
        return

    index_names = {idx["name"] for idx in inspector.get_indexes("locale_overrides")}
    if "uq_locale_overrides_locale_key" in index_names:
        op.drop_index("uq_locale_overrides_locale_key", table_name="locale_overrides")
