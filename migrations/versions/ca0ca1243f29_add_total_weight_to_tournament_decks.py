"""add total_weight to tournament_decks

Revision ID: ca0ca1243f29
Revises: d5d08df35003
Create Date: 2025-12-27 23:58:05.990028

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ca0ca1243f29'
down_revision: Union[str, None] = 'd5d08df35003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tournament_decks ADD COLUMN IF NOT EXISTS total_weight DOUBLE PRECISION NOT NULL DEFAULT 0"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE tournament_decks DROP COLUMN IF EXISTS total_weight")
