"""add on-chain NFT packs and cards schema (user_cards nft fields, pack_openings status/card_ids/nft_token_ids, pack_opening_commitments)

Revision ID: e7f8a9b0c1d2
Revises: b7c8d9e0f1a2
Create Date: 2026-03-02

Adds:
- user_cards: nft_token_id, chain_id, contract_address for on-chain card mapping.
- pack_openings: status (pending_mint/completed/failed), card_ids (JSON), nft_token_ids (JSON), pack_type_id (nullable, for prepare-open flow).
- New table pack_opening_commitments for commit-reveal (commitment_hash, server_seed, card_ids, status).
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE user_cards ADD COLUMN IF NOT EXISTS nft_token_id BIGINT")
    op.execute("ALTER TABLE user_cards ADD COLUMN IF NOT EXISTS chain_id INTEGER")
    op.execute("ALTER TABLE user_cards ADD COLUMN IF NOT EXISTS contract_address VARCHAR(42)")

    op.execute("ALTER TABLE pack_openings ALTER COLUMN pack_id DROP NOT NULL")

    op.execute(
        "ALTER TABLE pack_openings ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'completed'"
    )
    op.execute("ALTER TABLE pack_openings ADD COLUMN IF NOT EXISTS card_ids JSONB")
    op.execute("ALTER TABLE pack_openings ADD COLUMN IF NOT EXISTS nft_token_ids JSONB")
    op.execute("ALTER TABLE pack_openings ADD COLUMN IF NOT EXISTS pack_type_id INTEGER")

    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_pack_openings_pack_type_id'
            ) THEN
                ALTER TABLE pack_openings
                ADD CONSTRAINT fk_pack_openings_pack_type_id
                FOREIGN KEY (pack_type_id) REFERENCES pack_types(id);
            END IF;
        END $$;
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS pack_opening_commitments (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            pack_type_id INTEGER NOT NULL REFERENCES pack_types(id) ON DELETE CASCADE,
            commitment_hash VARCHAR(66) NOT NULL,
            server_seed BYTEA,
            card_ids JSONB,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_pack_opening_commitments_commitment_hash "
        "ON pack_opening_commitments (commitment_hash)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_pack_opening_commitments_user_id_status "
        "ON pack_opening_commitments (user_id, status)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_pack_opening_commitments_user_id_status")
    op.execute("DROP INDEX IF EXISTS ix_pack_opening_commitments_commitment_hash")
    op.execute("DROP TABLE IF EXISTS pack_opening_commitments")

    op.execute("ALTER TABLE pack_openings DROP CONSTRAINT IF EXISTS fk_pack_openings_pack_type_id")
    op.execute("ALTER TABLE pack_openings DROP COLUMN IF EXISTS pack_type_id")
    op.execute("ALTER TABLE pack_openings ALTER COLUMN pack_id SET NOT NULL")
    op.execute("ALTER TABLE pack_openings DROP COLUMN IF EXISTS nft_token_ids")
    op.execute("ALTER TABLE pack_openings DROP COLUMN IF EXISTS card_ids")
    op.execute("ALTER TABLE pack_openings DROP COLUMN IF EXISTS status")

    op.execute("ALTER TABLE user_cards DROP COLUMN IF EXISTS contract_address")
    op.execute("ALTER TABLE user_cards DROP COLUMN IF EXISTS chain_id")
    op.execute("ALTER TABLE user_cards DROP COLUMN IF EXISTS nft_token_id")
