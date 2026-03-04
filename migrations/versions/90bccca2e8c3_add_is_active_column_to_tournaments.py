"""add_is_active_column_to_tournaments

Revision ID: 90bccca2e8c3
Revises: 72161b1da687
Create Date: 2026-01-15 01:05:34.930947

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '90bccca2e8c3'
down_revision: Union[str, None] = '72161b1da687'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute("ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true")
    op.execute("UPDATE tournaments SET is_active = true WHERE is_active IS NULL")


def downgrade():
    op.execute("ALTER TABLE tournaments DROP COLUMN IF EXISTS is_active")