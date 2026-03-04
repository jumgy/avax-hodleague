"""add_card_rendering_fields

Revision ID: xxxxx
Revises: yyyyy
Create Date: 2024-xx-xx
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd8128ea7d0b0'
down_revision: Union[str, None] = 'ca0ca1243f29'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade():
    # Idempotent: add columns only if missing (e.g. table created via create_all).
    op.execute(
        "ALTER TABLE cards ADD COLUMN IF NOT EXISTS template_image_url VARCHAR(500)"
    )
    op.execute(
        "ALTER TABLE cards ADD COLUMN IF NOT EXISTS last_rendered_at TIMESTAMP WITHOUT TIME ZONE"
    )
    # Backfill template_image_url from background_image_url or rendered_image_url if present.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'cards' AND column_name = 'background_image_url') THEN
                UPDATE cards SET template_image_url = background_image_url WHERE template_image_url IS NULL AND background_image_url IS NOT NULL;
            ELSIF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'cards' AND column_name = 'rendered_image_url') THEN
                UPDATE cards SET template_image_url = rendered_image_url WHERE template_image_url IS NULL AND rendered_image_url IS NOT NULL;
            END IF;
        END $$;
    """)
    # Ensure NOT NULL: fill nulls then set constraint (no-op if already NOT NULL).
    op.execute("UPDATE cards SET template_image_url = '' WHERE template_image_url IS NULL")
    op.execute("ALTER TABLE cards ALTER COLUMN template_image_url SET NOT NULL")


def downgrade():
    op.execute("ALTER TABLE cards DROP COLUMN IF EXISTS last_rendered_at")
    op.execute("ALTER TABLE cards DROP COLUMN IF EXISTS template_image_url")
