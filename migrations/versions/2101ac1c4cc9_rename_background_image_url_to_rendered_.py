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
    # Rename column instead of drop/create
    op.alter_column('cards', 'background_image_url', 
                    new_column_name='rendered_image_url')

def downgrade() -> None:
    # Rollback rename
    op.alter_column('cards', 'rendered_image_url', 
                    new_column_name='background_image_url')