"""add server_seed to pack_openings for matching PackOpened events

Revision ID: f1a2b3c4d5e6
Revises: e7f8a9b0c1d2
Create Date: 2026-03-02

Allows event listener to match PackOpened(serverSeed) to the correct PackOpening record.
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE pack_openings ADD COLUMN IF NOT EXISTS server_seed BYTEA")

    op.execute("""
        CREATE TABLE IF NOT EXISTS pack_event_listener_state (
            id INTEGER PRIMARY KEY,
            last_block_number BIGINT NOT NULL DEFAULT 0,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute(
        "INSERT INTO pack_event_listener_state (id, last_block_number) VALUES (1, 0) "
        "ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS pack_event_listener_state")
    op.execute("ALTER TABLE pack_openings DROP COLUMN IF EXISTS server_seed")
