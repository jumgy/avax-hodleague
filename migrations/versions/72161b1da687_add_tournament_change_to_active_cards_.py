"""add_tournament_change_to_active_cards_view

Revision ID: 72161b1da687
Revises: e889ad79c5cd
Create Date: 2026-01-15 00:31:40.107709

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '72161b1da687'
down_revision: Union[str, None] = 'e889ad79c5cd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Drop existing view
    op.execute("DROP MATERIALIZED VIEW IF EXISTS active_cards_with_score")
    
    # Recreate view with tournament_change
    op.execute("""
        CREATE MATERIALIZED VIEW active_cards_with_score AS
        SELECT 
            c.id AS card_id,
            c.token_id,
            c.rarity_id,
            c.design_type,
            c.rendered_image_url,
            c.is_active,
            t.symbol AS token_symbol,
            t.name AS token_name,
            t.image_url AS token_image_url,
            t.weight AS token_weight,
            r.name AS rarity_name,
            r.color AS rarity_color,
            r.score_bonus AS rarity_score_bonus,
            tp.price AS current_price,
            tp.market_cap,
            tp.change_24h,
            tp.timestamp AS price_timestamp,
            COALESCE(
                CASE
                    WHEN tour.status = 'ongoing' AND ts.calculated_score IS NOT NULL 
                    THEN ts.calculated_score * r.score_bonus
                    ELSE 0
                END, 
                0
            ) AS calculated_score,
            tour.id AS active_tournament_id,
            tour.status AS tournament_status,
            -- ⭐ NEW: Tournament change (from snapshot to current)
            COALESCE(ts.price_change_percent, 0) AS tournament_change
        FROM cards c
        JOIN tokens t ON c.token_id = t.id
        JOIN rarities r ON c.rarity_id = r.id
        LEFT JOIN LATERAL (
            SELECT price, market_cap, change_24h, timestamp
            FROM token_prices
            WHERE token_id = t.id
            ORDER BY timestamp DESC
            LIMIT 1
        ) tp ON true
        LEFT JOIN LATERAL (
            SELECT id, status
            FROM tournaments
            WHERE status IN ('registration', 'ongoing')
            ORDER BY id DESC
            LIMIT 1
        ) tour ON true
        LEFT JOIN LATERAL (
            SELECT calculated_score, price_change_percent
            FROM token_scores
            WHERE token_id = t.id 
            AND tournament_id = tour.id
            ORDER BY calculated_at DESC
            LIMIT 1
        ) ts ON true
        WHERE c.is_active = true;
    """)
    
    # Recreate indexes
    op.execute("CREATE UNIQUE INDEX idx_active_cards_token_id ON active_cards_with_score(token_id)")
    op.execute("CREATE INDEX idx_active_cards_score_card_id ON active_cards_with_score(card_id)")
    op.execute("CREATE INDEX idx_active_cards_score_token_id ON active_cards_with_score(token_id)")
    op.execute("CREATE INDEX idx_active_cards_score_tournament ON active_cards_with_score(active_tournament_id)")

def downgrade():
    # Drop new view
    op.execute("DROP MATERIALIZED VIEW IF EXISTS active_cards_with_score")
    
    # Recreate old view (without tournament_change)
    op.execute("""
        CREATE MATERIALIZED VIEW active_cards_with_score AS
        SELECT 
            c.id AS card_id,
            c.token_id,
            c.rarity_id,
            c.design_type,
            c.rendered_image_url,
            c.is_active,
            t.symbol AS token_symbol,
            t.name AS token_name,
            t.image_url AS token_image_url,
            t.weight AS token_weight,
            r.name AS rarity_name,
            r.color AS rarity_color,
            r.score_bonus AS rarity_score_bonus,
            tp.price AS current_price,
            tp.market_cap,
            tp.change_24h,
            tp.timestamp AS price_timestamp,
            COALESCE(
                CASE
                    WHEN tour.status = 'ongoing' AND ts.calculated_score IS NOT NULL 
                    THEN ts.calculated_score * r.score_bonus
                    ELSE 0
                END, 
                0
            ) AS calculated_score,
            tour.id AS active_tournament_id,
            tour.status AS tournament_status
        FROM cards c
        JOIN tokens t ON c.token_id = t.id
        JOIN rarities r ON c.rarity_id = r.id
        LEFT JOIN LATERAL (
            SELECT price, market_cap, change_24h, timestamp
            FROM token_prices
            WHERE token_id = t.id
            ORDER BY timestamp DESC
            LIMIT 1
        ) tp ON true
        LEFT JOIN LATERAL (
            SELECT id, status
            FROM tournaments
            WHERE status IN ('registration', 'ongoing')
            ORDER BY id DESC
            LIMIT 1
        ) tour ON true
        LEFT JOIN LATERAL (
            SELECT calculated_score
            FROM token_scores
            WHERE token_id = t.id 
            AND tournament_id = tour.id
            ORDER BY calculated_at DESC
            LIMIT 1
        ) ts ON true
        WHERE c.is_active = true;
    """)
    
    # Recreate indexes
    op.execute("CREATE UNIQUE INDEX idx_active_cards_token_id ON active_cards_with_score(token_id)")
    op.execute("CREATE INDEX idx_active_cards_score_card_id ON active_cards_with_score(card_id)")
    op.execute("CREATE INDEX idx_active_cards_score_token_id ON active_cards_with_score(token_id)")
    op.execute("CREATE INDEX idx_active_cards_score_tournament ON active_cards_with_score(active_tournament_id)")