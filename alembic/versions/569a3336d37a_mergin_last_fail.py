"""mergin last fail

Revision ID: 569a3336d37a
Revises: d8137da72246, b1f7c52d4d8a
Create Date: 2026-02-26 11:57:12.724522

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '569a3336d37a'
down_revision: Union[str, Sequence[str], None] = ('d8137da72246', 'b1f7c52d4d8a')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
