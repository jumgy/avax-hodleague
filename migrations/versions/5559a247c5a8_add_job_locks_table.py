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
    # Create table for distributed locks
    op.create_table(
        'job_locks',
        sa.Column('job_name', sa.String(length=100), nullable=False),
        sa.Column('locked_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('locked_by', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('job_name')
    )
    
    # Index for fast lookup of expired locks
    op.create_index(
        'idx_job_locks_expires',
        'job_locks',
        ['expires_at']
    )


def downgrade() -> None:
    op.drop_index('idx_job_locks_expires', table_name='job_locks')
    op.drop_table('job_locks')