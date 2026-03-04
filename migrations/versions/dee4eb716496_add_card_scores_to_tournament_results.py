"""Add card_scores to tournament_results

Revision ID: dee4eb716496
Revises: f509f24e2d9c
Create Date: 2026-01-13 22:37:25.218181

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dee4eb716496'
down_revision: Union[str, None] = 'f509f24e2d9c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE tournament_results ADD COLUMN IF NOT EXISTS card_scores JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE tournament_results DROP COLUMN IF EXISTS card_scores")
