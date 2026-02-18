"""add registration_chain_id to tournament_decks

Revision ID: a1b2c3d4e5f6
Revises: 0693b506ba00
Create Date: 2026-02-18

Stores chain ID where user registered (2741 Abstract, 43114 Avalanche C-Chain).

After pulling: run `alembic upgrade head` to apply (see scripts/README.md).
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "0693b506ba00"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tournament_decks", sa.Column("registration_chain_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("tournament_decks", "registration_chain_id")
