"""add job locks table

Revision ID: 5559a247c5a8
Revises: 9ecc8d83fcc0
Create Date: 2026-01-22 21:35:56.021535

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5559a247c5a8'
down_revision: Union[str, None] = '9ecc8d83fcc0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS job_locks (
            job_name VARCHAR(100) NOT NULL PRIMARY KEY,
            locked_at TIMESTAMP WITH TIME ZONE NOT NULL,
            locked_by VARCHAR(255) NOT NULL,
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_job_locks_expires ON job_locks (expires_at)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_job_locks_expires")
    op.execute("DROP TABLE IF EXISTS job_locks")