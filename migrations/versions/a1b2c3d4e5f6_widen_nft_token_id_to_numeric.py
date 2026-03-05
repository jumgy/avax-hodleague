"""widen nft_token_id to numeric(78,0) for 256-bit token ids

Revision ID: ab12cd34ef56
Revises: e7f8a9b0c1d2
Create Date: 2026-03-05

This migration changes user_cards.nft_token_id from BIGINT to NUMERIC(78,0)
so we can safely store full 256-bit token IDs derived from keccak256.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ab12cd34ef56"
# Chain after all pack_openings off-chain fields:
# e7f8a9b0c1d2 -> f1a2b3c4d5e6 -> a2b3c4d5e6f7 -> b3c4d5e6f7a8 -> c4d5e6f7a8b9 -> ab12cd34ef56
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "user_cards",
        "nft_token_id",
        existing_type=sa.BigInteger(),
        type_=sa.Numeric(precision=78, scale=0),
        existing_nullable=True,
    )


def downgrade() -> None:
    # WARNING: Downgrading from NUMERIC(78,0) to BIGINT can overflow
    # for existing 256-bit token ids. This assumes either data was not
    # present or values fit into int64.
    op.alter_column(
        "user_cards",
        "nft_token_id",
        existing_type=sa.Numeric(precision=78, scale=0),
        type_=sa.BigInteger(),
        existing_nullable=True,
    )

