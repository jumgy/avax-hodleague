# migrations/versions/e9692c1c2418_fix_reward_models_datetime_timezone.py

"""Fix reward models datetime timezone

Revision ID: e9692c1c2418
Revises: 8e1ffece64de
Create Date: 2026-01-12 22:37:09.968120
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e9692c1c2418'
down_revision: Union[str, None] = '8e1ffece64de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Drop the view that depends on user_rewards
    op.execute("DROP VIEW IF EXISTS user_balances_view CASCADE")
    
    # Step 2: Alter column types
    op.alter_column('reward_types', 'created_at',
               existing_type=postgresql.TIMESTAMP(),
               type_=sa.DateTime(timezone=True),
               existing_nullable=False)
    op.alter_column('reward_types', 'updated_at',
               existing_type=postgresql.TIMESTAMP(),
               type_=sa.DateTime(timezone=True),
               existing_nullable=False)
    op.alter_column('user_rewards', 'earned_at',
               existing_type=postgresql.TIMESTAMP(),
               type_=sa.DateTime(timezone=True),
               existing_nullable=False)
    op.alter_column('user_rewards', 'claimed_at',
               existing_type=postgresql.TIMESTAMP(),
               type_=sa.DateTime(timezone=True),
               existing_nullable=True)
    op.alter_column('user_rewards', 'expires_at',
               existing_type=postgresql.TIMESTAMP(),
               type_=sa.DateTime(timezone=True),
               existing_nullable=True)
    
    # Step 3: Recreate the view
    op.execute("""
        CREATE VIEW user_balances_view AS
        SELECT 
            u.id as user_id,
            u.wallet_address,
            COALESCE(SUM(CASE WHEN ur.claim_status = 'claimed' THEN ur.amount ELSE 0 END), 0) as claimed_balance,
            COALESCE(SUM(CASE WHEN ur.claim_status = 'pending' THEN ur.amount ELSE 0 END), 0) as pending_balance,
            COALESCE(SUM(ur.amount), 0) as total_earned
        FROM users u
        LEFT JOIN user_rewards ur ON u.id = ur.user_id
        GROUP BY u.id, u.wallet_address
    """)


def downgrade() -> None:
    # Step 1: Drop the view
    op.execute("DROP VIEW IF EXISTS user_balances_view CASCADE")
    
    # Step 2: Revert column types
    op.alter_column('user_rewards', 'expires_at',
               existing_type=sa.DateTime(timezone=True),
               type_=postgresql.TIMESTAMP(),
               existing_nullable=True)
    op.alter_column('user_rewards', 'claimed_at',
               existing_type=sa.DateTime(timezone=True),
               type_=postgresql.TIMESTAMP(),
               existing_nullable=True)
    op.alter_column('user_rewards', 'earned_at',
               existing_type=sa.DateTime(timezone=True),
               type_=postgresql.TIMESTAMP(),
               existing_nullable=False)
    op.alter_column('reward_types', 'updated_at',
               existing_type=sa.DateTime(timezone=True),
               type_=postgresql.TIMESTAMP(),
               existing_nullable=False)
    op.alter_column('reward_types', 'created_at',
               existing_type=sa.DateTime(timezone=True),
               type_=postgresql.TIMESTAMP(),
               existing_nullable=False)
    
    # Step 3: Recreate the view with old column types
    op.execute("""
        CREATE VIEW user_balances_view AS
        SELECT 
            u.id as user_id,
            u.wallet_address,
            COALESCE(SUM(CASE WHEN ur.claim_status = 'claimed' THEN ur.amount ELSE 0 END), 0) as claimed_balance,
            COALESCE(SUM(CASE WHEN ur.claim_status = 'pending' THEN ur.amount ELSE 0 END), 0) as pending_balance,
            COALESCE(SUM(ur.amount), 0) as total_earned
        FROM users u
        LEFT JOIN user_rewards ur ON u.id = ur.user_id
        GROUP BY u.id, u.wallet_address
    """)