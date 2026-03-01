"""Fix all models datetime timezone

Revision ID: b6d321ba365a
Revises: e9692c1c2418
Create Date: 2026-01-13 18:35:09.121743

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = 'b6d321ba365a'
down_revision: Union[str, None] = 'e9692c1c2418'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def table_exists(table_name: str) -> bool:
    """Check that table exists."""
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    # STEP 0: Create audit_logs table if it doesn't exist
    if not table_exists('audit_logs'):
        print("✅ Creating audit_logs table...")
        op.create_table(
            'audit_logs',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('action_type', sa.String(length=50), nullable=False),
            sa.Column('entity_type', sa.String(length=50), nullable=False),
            sa.Column('entity_id', sa.Integer(), nullable=False),
            sa.Column('old_data', sa.JSON(), nullable=True),
            sa.Column('new_data', sa.JSON(), nullable=True),
            sa.Column('ip_address', sa.String(length=45), nullable=True),
            sa.Column('admin_id', sa.Integer(), nullable=True),
            sa.Column('transaction_hash', sa.String(length=66), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['admin_id'], ['users.id'], ),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_audit_logs_action_type', 'audit_logs', ['action_type'])
        op.create_index('ix_audit_logs_entity_type', 'audit_logs', ['entity_type'])
        op.create_index('ix_audit_logs_entity_id', 'audit_logs', ['entity_id'])
        op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])
        print("✅ audit_logs table created successfully")
    else:
        print("ℹ️  audit_logs table already exists")

    # STEP 1: Drop materialized view that depends on token_prices.timestamp
    op.execute("DROP MATERIALIZED VIEW IF EXISTS active_cards_with_score")

    # STEP 2: Alter all datetime columns to timezone-aware
    
    # audit_logs - now safe to alter
    if table_exists('audit_logs'):
        op.alter_column('audit_logs', 'created_at',
                   existing_type=postgresql.TIMESTAMP(),
                   type_=sa.DateTime(timezone=True),
                   existing_nullable=False)

    # card_weights
    if table_exists('card_weights'):
        op.alter_column('card_weights', 'last_updated',
                   existing_type=postgresql.TIMESTAMP(),
                   type_=sa.DateTime(timezone=True),
                   existing_nullable=False)

    # cards
    if table_exists('cards'):
        op.alter_column('cards', 'last_rendered_at',
                   existing_type=postgresql.TIMESTAMP(),
                   type_=sa.DateTime(timezone=True),
                   existing_nullable=True)
        op.alter_column('cards', 'created_at',
                   existing_type=postgresql.TIMESTAMP(),
                   type_=sa.DateTime(timezone=True),
                   existing_nullable=False)
        op.alter_column('cards', 'updated_at',
                   existing_type=postgresql.TIMESTAMP(),
                   type_=sa.DateTime(timezone=True),
                   existing_nullable=False)

    # pack_openings
    if table_exists('pack_openings'):
        op.alter_column('pack_openings', 'opened_at',
                   existing_type=postgresql.TIMESTAMP(),
                   type_=sa.DateTime(timezone=True),
                   existing_nullable=False)

    # pack_rarity_configs
    if table_exists('pack_rarity_configs'):
        op.alter_column('pack_rarity_configs', 'created_at',
                   existing_type=postgresql.TIMESTAMP(),
                   type_=sa.DateTime(timezone=True),
                   existing_nullable=False)
        op.alter_column('pack_rarity_configs', 'updated_at',
                   existing_type=postgresql.TIMESTAMP(),
                   type_=sa.DateTime(timezone=True),
                   existing_nullable=False)

    # pack_types
    if table_exists('pack_types'):
        op.alter_column('pack_types', 'available_from',
                   existing_type=postgresql.TIMESTAMP(),
                   type_=sa.DateTime(timezone=True),
                   existing_nullable=True)
        op.alter_column('pack_types', 'available_until',
                   existing_type=postgresql.TIMESTAMP(),
                   type_=sa.DateTime(timezone=True),
                   existing_nullable=True)
        op.alter_column('pack_types', 'created_at',
                   existing_type=postgresql.TIMESTAMP(),
                   type_=sa.DateTime(timezone=True),
                   existing_nullable=False)
        op.alter_column('pack_types', 'updated_at',
                   existing_type=postgresql.TIMESTAMP(),
                   type_=sa.DateTime(timezone=True),
                   existing_nullable=False)

    # rarities
    if table_exists('rarities'):
        op.alter_column('rarities', 'created_at',
                   existing_type=postgresql.TIMESTAMP(),
                   type_=sa.DateTime(timezone=True),
                   existing_nullable=False)
        op.alter_column('rarities', 'updated_at',
                   existing_type=postgresql.TIMESTAMP(),
                   type_=sa.DateTime(timezone=True),
                   existing_nullable=False)

    # token_prices (THE PROBLEMATIC ONE)
    if table_exists('token_prices'):
        op.alter_column('token_prices', 'timestamp',
                   existing_type=postgresql.TIMESTAMP(),
                   type_=sa.DateTime(timezone=True),
                   existing_nullable=False)

    # tokens
    if table_exists('tokens'):
        op.alter_column('tokens', 'created_at',
                   existing_type=postgresql.TIMESTAMP(),
                   type_=sa.DateTime(timezone=True),
                   existing_nullable=False)
        op.alter_column('tokens', 'updated_at',
                   existing_type=postgresql.TIMESTAMP(),
                   type_=sa.DateTime(timezone=True),
                   existing_nullable=False)

    # tournament_decks
    if table_exists('tournament_decks'):
        op.alter_column('tournament_decks', 'submitted_at',
                   existing_type=postgresql.TIMESTAMP(),
                   type_=sa.DateTime(timezone=True),
                   existing_nullable=False)

    # tournament_prize_config
    if table_exists('tournament_prize_config'):
        op.alter_column('tournament_prize_config', 'created_at',
                   existing_type=postgresql.TIMESTAMP(),
                   type_=sa.DateTime(timezone=True),
                   existing_nullable=False)

    # user_cards
    if table_exists('user_cards'):
        op.alter_column('user_cards', 'obtained_at',
                   existing_type=postgresql.TIMESTAMP(),
                   type_=sa.DateTime(timezone=True),
                   existing_nullable=False)
        op.alter_column('user_cards', 'expires_at',
                   existing_type=postgresql.TIMESTAMP(),
                   type_=sa.DateTime(timezone=True),
                   existing_nullable=True)
        op.alter_column('user_cards', 'created_at',
                   existing_type=postgresql.TIMESTAMP(),
                   type_=sa.DateTime(timezone=True),
                   existing_nullable=False)

    # user_packs
    if table_exists('user_packs'):
        op.alter_column('user_packs', 'obtained_at',
                   existing_type=postgresql.TIMESTAMP(),
                   type_=sa.DateTime(timezone=True),
                   existing_nullable=False)
        op.alter_column('user_packs', 'created_at',
                   existing_type=postgresql.TIMESTAMP(),
                   type_=sa.DateTime(timezone=True),
                   existing_nullable=False)

    # users
    if table_exists('users'):
        op.alter_column('users', 'created_at',
                   existing_type=postgresql.TIMESTAMP(),
                   type_=sa.DateTime(timezone=True),
                   existing_nullable=False)
        op.alter_column('users', 'updated_at',
                   existing_type=postgresql.TIMESTAMP(),
                   type_=sa.DateTime(timezone=True),
                   existing_nullable=False)

    # STEP 3: Recreate materialized view with updated timestamp type
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
                    WHEN tour.status = 'ongoing' AND tts.snapshot_price IS NOT NULL 
                    THEN (tp.price / tts.snapshot_price - 1) * 100 + r.score_bonus
                    ELSE 0
                END, 0
            ) AS calculated_score,
            tour.id AS active_tournament_id,
            tour.status AS tournament_status
        FROM cards c
        JOIN tokens t ON c.token_id = t.id
        JOIN rarities r ON c.rarity_id = r.id
        LEFT JOIN LATERAL (
            SELECT price, market_cap, change_24h, timestamp
            FROM token_prices
            WHERE token_id = c.token_id
            ORDER BY timestamp DESC
            LIMIT 1
        ) tp ON true
        LEFT JOIN tournaments tour ON tour.status IN ('registration', 'ongoing')
        LEFT JOIN tournament_token_snapshots tts ON tts.tournament_id = tour.id AND tts.token_id = c.token_id
        WHERE c.is_active = true
    """)

    # STEP 4: Recreate index
    op.create_index('idx_active_cards_score_card_id', 'active_cards_with_score', ['card_id'])
    
    print("✅ Migration completed successfully!")


def downgrade() -> None:
    # Drop view first
    op.execute("DROP MATERIALIZED VIEW IF EXISTS active_cards_with_score")

    # Revert all columns back to TIMESTAMP without timezone
    if table_exists('users'):
        op.alter_column('users', 'updated_at',
                   existing_type=sa.DateTime(timezone=True),
                   type_=postgresql.TIMESTAMP(),
                   existing_nullable=False)
        op.alter_column('users', 'created_at',
                   existing_type=sa.DateTime(timezone=True),
                   type_=postgresql.TIMESTAMP(),
                   existing_nullable=False)

    if table_exists('user_packs'):
        op.alter_column('user_packs', 'created_at',
                   existing_type=sa.DateTime(timezone=True),
                   type_=postgresql.TIMESTAMP(),
                   existing_nullable=False)
        op.alter_column('user_packs', 'obtained_at',
                   existing_type=sa.DateTime(timezone=True),
                   type_=postgresql.TIMESTAMP(),
                   existing_nullable=False)

    if table_exists('user_cards'):
        op.alter_column('user_cards', 'created_at',
                   existing_type=sa.DateTime(timezone=True),
                   type_=postgresql.TIMESTAMP(),
                   existing_nullable=False)
        op.alter_column('user_cards', 'expires_at',
                   existing_type=sa.DateTime(timezone=True),
                   type_=postgresql.TIMESTAMP(),
                   existing_nullable=True)
        op.alter_column('user_cards', 'obtained_at',
                   existing_type=sa.DateTime(timezone=True),
                   type_=postgresql.TIMESTAMP(),
                   existing_nullable=False)

    if table_exists('tournament_prize_config'):
        op.alter_column('tournament_prize_config', 'created_at',
                   existing_type=sa.DateTime(timezone=True),
                   type_=postgresql.TIMESTAMP(),
                   existing_nullable=False)

    if table_exists('tournament_decks'):
        op.alter_column('tournament_decks', 'submitted_at',
                   existing_type=sa.DateTime(timezone=True),
                   type_=postgresql.TIMESTAMP(),
                   existing_nullable=False)

    if table_exists('tokens'):
        op.alter_column('tokens', 'updated_at',
                   existing_type=sa.DateTime(timezone=True),
                   type_=postgresql.TIMESTAMP(),
                   existing_nullable=False)
        op.alter_column('tokens', 'created_at',
                   existing_type=sa.DateTime(timezone=True),
                   type_=postgresql.TIMESTAMP(),
                   existing_nullable=False)

    if table_exists('token_prices'):
        op.alter_column('token_prices', 'timestamp',
                   existing_type=sa.DateTime(timezone=True),
                   type_=postgresql.TIMESTAMP(),
                   existing_nullable=False)

    if table_exists('rarities'):
        op.alter_column('rarities', 'updated_at',
                   existing_type=sa.DateTime(timezone=True),
                   type_=postgresql.TIMESTAMP(),
                   existing_nullable=False)
        op.alter_column('rarities', 'created_at',
                   existing_type=sa.DateTime(timezone=True),
                   type_=postgresql.TIMESTAMP(),
                   existing_nullable=False)

    if table_exists('pack_types'):
        op.alter_column('pack_types', 'updated_at',
                   existing_type=sa.DateTime(timezone=True),
                   type_=postgresql.TIMESTAMP(),
                   existing_nullable=False)
        op.alter_column('pack_types', 'created_at',
                   existing_type=sa.DateTime(timezone=True),
                   type_=postgresql.TIMESTAMP(),
                   existing_nullable=False)
        op.alter_column('pack_types', 'available_until',
                   existing_type=sa.DateTime(timezone=True),
                   type_=postgresql.TIMESTAMP(),
                   existing_nullable=True)
        op.alter_column('pack_types', 'available_from',
                   existing_type=sa.DateTime(timezone=True),
                   type_=postgresql.TIMESTAMP(),
                   existing_nullable=True)

    if table_exists('pack_rarity_configs'):
        op.alter_column('pack_rarity_configs', 'updated_at',
                   existing_type=sa.DateTime(timezone=True),
                   type_=postgresql.TIMESTAMP(),
                   existing_nullable=False)
        op.alter_column('pack_rarity_configs', 'created_at',
                   existing_type=sa.DateTime(timezone=True),
                   type_=postgresql.TIMESTAMP(),
                   existing_nullable=False)

    if table_exists('pack_openings'):
        op.alter_column('pack_openings', 'opened_at',
                   existing_type=sa.DateTime(timezone=True),
                   type_=postgresql.TIMESTAMP(),
                   existing_nullable=False)

    if table_exists('cards'):
        op.alter_column('cards', 'updated_at',
                   existing_type=sa.DateTime(timezone=True),
                   type_=postgresql.TIMESTAMP(),
                   existing_nullable=False)
        op.alter_column('cards', 'created_at',
                   existing_type=sa.DateTime(timezone=True),
                   type_=postgresql.TIMESTAMP(),
                   existing_nullable=False)
        op.alter_column('cards', 'last_rendered_at',
                   existing_type=sa.DateTime(timezone=True),
                   type_=postgresql.TIMESTAMP(),
                   existing_nullable=True)

    if table_exists('card_weights'):
        op.alter_column('card_weights', 'last_updated',
                   existing_type=sa.DateTime(timezone=True),
                   type_=postgresql.TIMESTAMP(),
                   existing_nullable=False)

    if table_exists('audit_logs'):
        op.alter_column('audit_logs', 'created_at',
                   existing_type=sa.DateTime(timezone=True),
                   type_=postgresql.TIMESTAMP(),
                   existing_nullable=False)

    # Recreate old view
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
                    WHEN tour.status = 'ongoing' AND tts.snapshot_price IS NOT NULL 
                    THEN (tp.price / tts.snapshot_price - 1) * 100 + r.score_bonus
                    ELSE 0
                END, 0
            ) AS calculated_score,
            tour.id AS active_tournament_id,
            tour.status AS tournament_status
        FROM cards c
        JOIN tokens t ON c.token_id = t.id
        JOIN rarities r ON c.rarity_id = r.id
        LEFT JOIN LATERAL (
            SELECT price, market_cap, change_24h, timestamp
            FROM token_prices
            WHERE token_id = c.token_id
            ORDER BY timestamp DESC
            LIMIT 1
        ) tp ON true
        LEFT JOIN tournaments tour ON tour.status IN ('registration', 'ongoing')
        LEFT JOIN tournament_token_snapshots tts ON tts.tournament_id = tour.id AND tts.token_id = c.token_id
        WHERE c.is_active = true
    """)

    # Recreate index
    op.create_index('idx_active_cards_score_card_id', 'active_cards_with_score', ['card_id'])
    
    # Drop audit_logs table if it was created by this migration
    # Note: We don't drop it in downgrade to preserve data
    # If you want to drop it, uncomment:
    # if table_exists('audit_logs'):
    #     op.drop_table('audit_logs')
