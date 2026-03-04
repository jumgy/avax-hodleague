"""add expires_at to user_packs

Revision ID: d0e53fc336c6
Revises: d55db82da219
Create Date: 2026-02-10 23:44:31.307015

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd0e53fc336c6'
down_revision: Union[str, None] = 'd55db82da219'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE user_packs ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP WITH TIME ZONE")


def downgrade() -> None:
    op.execute("ALTER TABLE user_packs DROP COLUMN IF EXISTS expires_at")
