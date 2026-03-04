"""Rename background_image_url to rendered_image_url in cards table

Revision ID: 2101ac1c4cc9
Revises: 7995da6e0dde
Create Date: 2025-12-30 00:21:13.631389

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '2101ac1c4cc9'
down_revision: Union[str, None] = '7995da6e0dde'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Idempotent: rename only if background_image_url exists (skip if rendered_image_url already from create_all).
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'cards' AND column_name = 'background_image_url')
               AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'cards' AND column_name = 'rendered_image_url') THEN
                ALTER TABLE cards RENAME COLUMN background_image_url TO rendered_image_url;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'cards' AND column_name = 'rendered_image_url')
               AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'cards' AND column_name = 'background_image_url') THEN
                ALTER TABLE cards RENAME COLUMN rendered_image_url TO background_image_url;
            END IF;
        END $$;
    """)