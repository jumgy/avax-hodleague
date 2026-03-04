"""Update active_cards_with_score view with rendered_image_url

Revision ID: 62722b7f6702
Revises: 2101ac1c4cc9
Create Date: (set when generating)

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '62722b7f6702'
down_revision: Union[str, None] = '2101ac1c4cc9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Drop old view
    op.execute("DROP MATERIALIZED VIEW IF EXISTS active_cards_with_score CASCADE")
    
    # Recreate with new column name
    op.execute("""
        CREATE MATERIALIZED VIEW active_cards_with_score AS
        SELECT 
            c.id as card_id,
            c.token_id,
            c.rarity_id,
            c.design_type,
            c.rendered_image_url,  -- CHANGED FROM background_image_url
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
    
    # Recreate index
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_active_cards_score_card_id 
        ON active_cards_with_score(card_id)
    """)

def downgrade() -> None:
    # Drop view
    op.execute("DROP MATERIALIZED VIEW IF EXISTS active_cards_with_score CASCADE")
    
    # Recreate with old column name
    op.execute("""
        CREATE MATERIALIZED VIEW active_cards_with_score AS
        SELECT 
            c.id as card_id,
            c.token_id,
            c.rarity_id,
            c.design_type,
            c.background_image_url,  -- OLD NAME
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
            -- Score calculation
            COALESCE(
                CASE 
                    WHEN tour.status = 'ongoing' AND tts.snapshot_price IS NOT NULL THEN
                        ((tp.price / tts.snapshot_price) - 1) * 100 + r.score_bonus
                    ELSE 0
                END,
                0
            ) as calculated_score,
            -- Tournament info
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
    
    # Recreate index
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_active_cards_score_card_id 
        ON active_cards_with_score(card_id)
    """)