"""add_index_to_materialized_view

Revision ID: e889ad79c5cd
Revises: f482043a2fed
Create Date: 2026-01-14 00:10:55.916895

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e889ad79c5cd'
down_revision: Union[str, None] = 'f482043a2fed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_active_cards_token_id 
        ON active_cards_with_score (token_id);
    """)
def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_active_cards_token_id;")
