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
    # Делаем background_image_url nullable
    op.alter_column('cards', 'background_image_url',
                    existing_type=sa.String(length=500),
                    nullable=True)

def downgrade():
    # Откат - делаем NOT NULL обратно
    op.alter_column('cards', 'background_image_url',
                    existing_type=sa.String(length=500),
                    nullable=False)