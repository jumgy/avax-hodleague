"""fix user_balance_view

Revision ID: f482043a2fed
Revises: 027ebe7dde27
Create Date: 2026-01-13 23:29:55.070435

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f482043a2fed'
down_revision: Union[str, None] = '027ebe7dde27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS user_balances_view CASCADE")
    op.execute("""
        CREATE VIEW user_balances_view AS
        SELECT 
            ur.user_id,
            rt.reward_category,
            rt.currency_type,
            COALESCE(SUM(CASE WHEN ur.claim_status = 'claimed' THEN ur.amount ELSE 0 END), 0) as available_balance,
            COALESCE(SUM(CASE WHEN ur.claim_status = 'pending' THEN ur.amount ELSE 0 END), 0) as pending_balance,
            COUNT(CASE WHEN ur.claim_status = 'pending' THEN 1 END) as pending_count,
            COUNT(CASE WHEN ur.claim_status = 'claimed' THEN 1 END) as claimed_count,
            MAX(ur.earned_at) as last_reward_date
        FROM user_rewards ur
        JOIN reward_types rt ON ur.reward_type_id = rt.id
        WHERE rt.is_active = true 
          AND (ur.expires_at IS NULL OR ur.expires_at > NOW())
        GROUP BY ur.user_id, rt.reward_category, rt.currency_type
        ORDER BY ur.user_id, rt.reward_category
    """)

def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS user_balances_view CASCADE")
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
