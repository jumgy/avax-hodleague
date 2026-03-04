"""add prize amount to tournamet model

Revision ID: e6ddbd9eb0bb
Revises: 90bccca2e8c3
Create Date: 2026-01-18 20:55:30.083437

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6ddbd9eb0bb'
down_revision: Union[str, None] = '90bccca2e8c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS prize_amount NUMERIC(20, 2)")


def downgrade() -> None:
    op.execute("ALTER TABLE tournaments DROP COLUMN IF EXISTS prize_amount")
