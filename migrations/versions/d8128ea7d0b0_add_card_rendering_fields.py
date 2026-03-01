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
    # Add new columns
    op.add_column('cards', sa.Column('template_image_url', sa.String(length=500), nullable=True))
    op.add_column('cards', sa.Column('last_rendered_at', sa.DateTime(), nullable=True))
    
    # Copy data from background_image_url to template_image_url
    op.execute("UPDATE cards SET template_image_url = background_image_url WHERE template_image_url IS NULL")
    
    # Make template_image_url NOT NULL after backfill
    op.alter_column('cards', 'template_image_url', nullable=False)

def downgrade():
    # Downgrade migration
    op.drop_column('cards', 'last_rendered_at')
    op.drop_column('cards', 'template_image_url')
