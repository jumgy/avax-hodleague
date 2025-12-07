"""Add user_balances_view

Revision ID: 25958854386e
Revises: af38c55b9daf
Create Date: 2025-12-07 01:09:21.091360

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '25958854386e'
down_revision: Union[str, None] = 'af38c55b9daf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Создание представления user_balances_view
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
        AND ur.expires_at IS NULL OR ur.expires_at > NOW()
        GROUP BY ur.user_id, rt.reward_category, rt.currency_type
        ORDER BY ur.user_id, rt.reward_category;
    """)

def downgrade() -> None:
    # Удаление представления
    op.execute("DROP VIEW IF EXISTS user_balances_view;")