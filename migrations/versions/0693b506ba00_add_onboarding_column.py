"""add onboarding column

Revision ID: 0693b506ba00
Revises: d0e53fc336c6
Create Date: 2026-02-11 23:23:27.555170

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0693b506ba00'
down_revision: Union[str, None] = 'd0e53fc336c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_steps JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS onboarding_steps")
