"""add locale override unique index

Revision ID: b1f7c52d4d8a
Revises: cc400eadf331
Create Date: 2026-02-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b1f7c52d4d8a"
down_revision: Union[str, Sequence[str], None] = "cc400eadf331"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_locale_overrides_locale_key",
        "locale_overrides",
        ["locale", "key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_locale_overrides_locale_key", table_name="locale_overrides")
