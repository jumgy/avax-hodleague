"""Add weight to token score

Revision ID: d55db82da219
Revises: 7038e0042b9c
Create Date: 2026-02-07 20:38:09.831496

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd55db82da219'
down_revision: Union[str, None] = '7038e0042b9c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE token_scores ADD COLUMN IF NOT EXISTS weight INTEGER")
    op.execute("DROP INDEX IF EXISTS idx_users_referred_by")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS fk_users_referred_by")
    op.execute("ALTER TABLE users ADD CONSTRAINT fk_users_referred_by FOREIGN KEY (referred_by_id) REFERENCES users(id) ON DELETE SET NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS fk_users_referred_by")
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT fk_users_referred_by "
        "FOREIGN KEY (referred_by_id) REFERENCES users(id) ON DELETE SET NULL"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_referred_by ON users (referred_by_id)")
    op.execute("ALTER TABLE token_scores DROP COLUMN IF EXISTS weight")
