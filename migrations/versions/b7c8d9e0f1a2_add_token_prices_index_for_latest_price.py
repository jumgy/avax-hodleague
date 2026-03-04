"""add index token_prices (token_id, timestamp desc) for leaderboard

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-02-20

Speeds up "latest price per token" query in tokens list/leaderboard endpoint.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_token_prices_token_id_timestamp_desc
        ON token_prices (token_id, timestamp DESC);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_token_prices_token_id_timestamp_desc;")
