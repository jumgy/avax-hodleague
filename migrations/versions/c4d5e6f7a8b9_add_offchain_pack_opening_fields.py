"""add off-chain pack opening fields (server_seed_hash, client_seed, combined_hash, signature)

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-03-03

For prepare_open_offchain we store provably-fair seeds and backend signature.
Existing rows get default values so NOT NULL is satisfied.
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 32 zero bytes in hex for default BYTEA
DEFAULT_32_BYTES_HEX = "0000000000000000" * 4


def upgrade() -> None:
    op.execute(
        "ALTER TABLE pack_openings ADD COLUMN IF NOT EXISTS server_seed_hash BYTEA "
        f"NOT NULL DEFAULT decode('{DEFAULT_32_BYTES_HEX}', 'hex')"
    )
    op.execute(
        "ALTER TABLE pack_openings ADD COLUMN IF NOT EXISTS client_seed BYTEA "
        f"NOT NULL DEFAULT decode('{DEFAULT_32_BYTES_HEX}', 'hex')"
    )
    op.execute(
        "ALTER TABLE pack_openings ADD COLUMN IF NOT EXISTS combined_hash BYTEA "
        f"NOT NULL DEFAULT decode('{DEFAULT_32_BYTES_HEX}', 'hex')"
    )
    op.execute(
        "ALTER TABLE pack_openings ADD COLUMN IF NOT EXISTS signature BYTEA NOT NULL DEFAULT ''::bytea"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE pack_openings DROP COLUMN IF EXISTS signature")
    op.execute("ALTER TABLE pack_openings DROP COLUMN IF EXISTS combined_hash")
    op.execute("ALTER TABLE pack_openings DROP COLUMN IF EXISTS client_seed")
    op.execute("ALTER TABLE pack_openings DROP COLUMN IF EXISTS server_seed_hash")
