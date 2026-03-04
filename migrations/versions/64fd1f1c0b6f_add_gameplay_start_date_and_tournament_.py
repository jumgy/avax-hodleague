"""Add gameplay start date and tournament token snapshots

Revision ID: 64fd1f1c0b6f
Revises: 25958854386e
Create Date: 2025-12-20 20:31:37.936001

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '64fd1f1c0b6f'
down_revision: Union[str, None] = '25958854386e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: skip if column already exists (e.g. DB was partially migrated or restored).
    op.execute(
        "ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS gameplay_start_date TIMESTAMP WITHOUT TIME ZONE"
    )
    
    # Create materialized view for active cards with scores.
    # Use rendered_image_url (current column name; was background_image_url in older migrations).
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS active_cards_with_score AS
        SELECT 
            c.id as card_id,
            c.token_id,
            c.rarity_id,
            c.design_type,
            c.rendered_image_url,
            c.is_active,
            
            -- Token info
            t.symbol as token_symbol,
            t.name as token_name,
            t.image_url as token_image_url,
            t.weight as token_weight,
            
            -- Rarity info
            r.name as rarity_name,
            r.color as rarity_color,
            r.score_bonus as rarity_score_bonus,
            
            -- Latest price info
            tp.price as current_price,
            tp.market_cap,
            tp.change_24h,
            tp.timestamp as price_timestamp,
            
            -- Score calculation (will be 0 if no active tournament)
            COALESCE(
                CASE 
                    WHEN tour.status = 'ongoing' AND tts.snapshot_price IS NOT NULL THEN
                        ((tp.price / tts.snapshot_price) - 1) * 100 + r.score_bonus
                    ELSE 0
                END,
                0
            ) as calculated_score,
            
            -- Tournament info for context
            tour.id as active_tournament_id,
            tour.status as tournament_status
            
        FROM cards c
        INNER JOIN tokens t ON c.token_id = t.id
        INNER JOIN rarities r ON c.rarity_id = r.id
        LEFT JOIN LATERAL (
            SELECT price, market_cap, change_24h, timestamp
            FROM token_prices
            WHERE token_id = c.token_id
            ORDER BY timestamp DESC
            LIMIT 1
        ) tp ON true
        LEFT JOIN tournaments tour ON tour.status IN ('registration', 'ongoing')
        LEFT JOIN tournament_token_snapshots tts 
            ON tts.tournament_id = tour.id AND tts.token_id = c.token_id
        WHERE c.is_active = true
    """)
    
    # Create index on materialized view for faster queries
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_active_cards_score_card_id 
        ON active_cards_with_score(card_id)
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE tournaments DROP COLUMN IF EXISTS gameplay_start_date")
    
    # Drop materialized view
    op.execute("DROP MATERIALIZED VIEW IF EXISTS active_cards_with_score")