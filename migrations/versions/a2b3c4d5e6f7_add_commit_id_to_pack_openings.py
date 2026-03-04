"""add commit_id to pack_openings for two-step commit-reveal

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-03-03

prepare-open now requires commit_id (from PackCommitted). PackOpening stores
commit_id to match PackRevealed events.
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE pack_openings ADD COLUMN IF NOT EXISTS commit_id BIGINT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE pack_openings DROP COLUMN IF EXISTS commit_id")
