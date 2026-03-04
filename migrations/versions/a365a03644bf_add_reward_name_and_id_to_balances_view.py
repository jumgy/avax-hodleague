"""add_reward_name_and_id_to_balances_view

Revision ID: a365a03644bf
Revises: 0733888b351a
Create Date: 2026-01-29 00:16:17.170916

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a365a03644bf'
down_revision: Union[str, None] = '0733888b351a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Recreate user_balances_view with reward_name and reward_type_id fields.
    Also fix grouping to separate different reward types properly.
    """
    
    # Drop existing view
    op.execute("DROP VIEW IF EXISTS user_balances_view CASCADE")
    
    # Create improved view
    op.execute("""
        CREATE VIEW user_balances_view AS
        SELECT 
            ur.user_id,
            rt.reward_category,
            rt.currency_type,
            rt.name AS reward_name,
            rt.id AS reward_type_id,
            
            -- Available balance (claimed rewards)
            COALESCE(SUM(
                CASE
                    WHEN ur.claim_status = 'claimed' THEN ur.amount
                    ELSE 0
                END
            ), 0) AS available_balance,
            
            -- Pending balance (claimable rewards, not expired)
            COALESCE(SUM(
                CASE
                    WHEN ur.claim_status = 'pending' 
                        AND (ur.expires_at IS NULL OR ur.expires_at > NOW())
                    THEN ur.amount
                    ELSE 0
                END
            ), 0) AS pending_balance,
            
            -- Count of pending rewards
            COUNT(
                CASE
                    WHEN ur.claim_status = 'pending'
                        AND (ur.expires_at IS NULL OR ur.expires_at > NOW())
                    THEN 1
                END
            ) AS pending_count,
            
            -- Count of claimed rewards
            COUNT(
                CASE
                    WHEN ur.claim_status = 'claimed' THEN 1
                END
            ) AS claimed_count,
            
            -- Last reward earned date
            MAX(ur.earned_at) AS last_reward_date
            
        FROM user_rewards ur
        INNER JOIN reward_types rt ON ur.reward_type_id = rt.id
        WHERE rt.is_active = TRUE
        GROUP BY 
            ur.user_id, 
            rt.reward_category, 
            rt.currency_type,
            rt.name,
            rt.id
        ORDER BY 
            ur.user_id, 
            rt.reward_category,
            rt.name
    """)
    
    # Add comment to view
    op.execute("""
        COMMENT ON VIEW user_balances_view IS 
        'User balance aggregation by reward type. Shows available (claimed) and pending balances with full reward type information (name, id, category).'
    """)


def downgrade() -> None:
    """
    Restore original view without reward_name and reward_type_id.
    """
    
    # Drop modified view
    op.execute("DROP VIEW IF EXISTS user_balances_view CASCADE")
    
    # Restore original view
    op.execute("""
        CREATE VIEW user_balances_view AS
        SELECT 
            ur.user_id,
            rt.reward_category,
            rt.currency_type,
            COALESCE(SUM(
                CASE
                    WHEN ur.claim_status = 'claimed' THEN ur.amount
                    ELSE 0
                END
            ), 0) AS available_balance,
            COALESCE(SUM(
                CASE
                    WHEN ur.claim_status = 'pending' THEN ur.amount
                    ELSE 0
                END
            ), 0) AS pending_balance,
            COUNT(
                CASE
                    WHEN ur.claim_status = 'pending' THEN 1
                END
            ) AS pending_count,
            COUNT(
                CASE
                    WHEN ur.claim_status = 'claimed' THEN 1
                END
            ) AS claimed_count,
            MAX(ur.earned_at) AS last_reward_date
        FROM user_rewards ur
        JOIN reward_types rt ON ur.reward_type_id = rt.id
        WHERE rt.is_active = TRUE 
            AND (ur.expires_at IS NULL OR ur.expires_at > NOW())
        GROUP BY ur.user_id, rt.reward_category, rt.currency_type
        ORDER BY ur.user_id, rt.reward_category
    """)