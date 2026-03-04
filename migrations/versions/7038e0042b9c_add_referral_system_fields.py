"""Add referral system fields

Revision ID: 7038e0042b9c
Revises: a365a03644bf
Create Date: 2026-02-06 21:01:03.708114

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7038e0042b9c'
down_revision: Union[str, None] = 'a365a03644bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by_id INTEGER")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS fk_users_referred_by")
    op.execute("ALTER TABLE users ADD CONSTRAINT fk_users_referred_by FOREIGN KEY (referred_by_id) REFERENCES users(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_count INTEGER NOT NULL DEFAULT 0")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_referred_by ON users (referred_by_id)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_users_referred_by")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS referral_count")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS fk_users_referred_by")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS referred_by_id")
