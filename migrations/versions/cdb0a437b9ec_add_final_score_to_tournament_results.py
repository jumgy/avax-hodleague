"""Add final score to tournament results

Revision ID: cdb0a437b9ec
Revises: 64fd1f1c0b6f
Create Date: 2025-12-20 20:46:25.231570

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cdb0a437b9ec'
down_revision: Union[str, None] = '64fd1f1c0b6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: skip if column already exists (e.g. table created via create_all with current model).
    op.execute(
        "ALTER TABLE tournament_results ADD COLUMN IF NOT EXISTS final_score NUMERIC(20, 4) NOT NULL DEFAULT 0"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE tournament_results DROP COLUMN IF EXISTS final_score")
