"""add_prize_distribution_fields

Revision ID: 9ecc8d83fcc0
Revises: e6ddbd9eb0bb
Create Date: 2026-01-18 21:12:13.312321

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9ecc8d83fcc0'
down_revision: Union[str, None] = 'e6ddbd9eb0bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE tournament_results ADD COLUMN IF NOT EXISTS prizes JSONB")
    op.execute("ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS reward_types JSONB")
    op.execute("ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS prize_pools JSONB")
    op.execute("ALTER TABLE tournaments DROP COLUMN IF EXISTS prize_amount")


def downgrade() -> None:
    op.execute("ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS prize_amount NUMERIC(20, 2)")
    op.execute("ALTER TABLE tournaments DROP COLUMN IF EXISTS prize_pools")
    op.execute("ALTER TABLE tournaments DROP COLUMN IF EXISTS reward_types")
    op.execute("ALTER TABLE tournament_results DROP COLUMN IF EXISTS prizes")
