"""make_background_image_url_nullable

Revision ID: 7995da6e0dde
Revises: d8128ea7d0b0
Create Date: 2025-12-29 21:38:58.793092

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7995da6e0dde'
down_revision: Union[str, None] = 'd8128ea7d0b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade():
    # Make image URL column nullable (idempotent: column may be background_image_url or rendered_image_url).
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'cards' AND column_name = 'background_image_url') THEN
                ALTER TABLE cards ALTER COLUMN background_image_url DROP NOT NULL;
            ELSIF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'cards' AND column_name = 'rendered_image_url') THEN
                ALTER TABLE cards ALTER COLUMN rendered_image_url DROP NOT NULL;
            END IF;
        END $$;
    """)


def downgrade():
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'cards' AND column_name = 'background_image_url') THEN
                ALTER TABLE cards ALTER COLUMN background_image_url SET NOT NULL;
            ELSIF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'cards' AND column_name = 'rendered_image_url') THEN
                ALTER TABLE cards ALTER COLUMN rendered_image_url SET NOT NULL;
            END IF;
        END $$;
    """)