"""merge products limit and property index heads

Revision ID: c9f1e4a2d8b6
Revises: 2d4a6b8c9e10, a5c2d9e7b341
Create Date: 2026-04-10 19:10:00.000000

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "c9f1e4a2d8b6"
down_revision: Union[str, Sequence[str], None] = ("2d4a6b8c9e10", "a5c2d9e7b341")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
