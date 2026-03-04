"""add relayer_tx_hash to pack_openings for abandoned-commit job

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-03-03

When the job submits relayerRevealOpen we store the tx hash so we do not resubmit.
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE pack_openings ADD COLUMN IF NOT EXISTS relayer_tx_hash VARCHAR(66)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE pack_openings DROP COLUMN IF EXISTS relayer_tx_hash")
