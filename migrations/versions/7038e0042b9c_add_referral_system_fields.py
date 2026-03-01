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
    # Add referred_by_id (nullable, FK)
    op.add_column('users', sa.Column('referred_by_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_users_referred_by',
        'users', 'users',
        ['referred_by_id'], ['id'],
        ondelete='SET NULL'
    )
    
    # Add referral_count with DEFAULT 0
    op.add_column('users', sa.Column('referral_count', sa.Integer(), nullable=False, server_default='0'))
    
    # Create index
    op.create_index('idx_users_referred_by', 'users', ['referred_by_id'])
def downgrade():
    op.drop_index('idx_users_referred_by', table_name='users')
    op.drop_column('users', 'referral_count')
    op.drop_constraint('fk_users_referred_by', 'users', type_='foreignkey')
    op.drop_column('users', 'referred_by_id')
