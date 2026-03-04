"""Add token_scores table for historical scoring

Revision ID: 1683566ccf30
Revises: b6d321ba365a
Create Date: 2026-01-13 19:10:07.338938

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1683566ccf30'
down_revision: Union[str, None] = 'b6d321ba365a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS token_scores (
            id SERIAL NOT NULL,
            tournament_id INTEGER NOT NULL,
            token_id INTEGER NOT NULL,
            calculated_score NUMERIC(20, 4) NOT NULL,
            current_price NUMERIC(20, 8),
            snapshot_price NUMERIC(20, 8),
            price_change_percent NUMERIC(10, 4),
            calculated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY (token_id) REFERENCES tokens (id),
            FOREIGN KEY (tournament_id) REFERENCES tournaments (id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_token_scores_calculated_at ON token_scores (calculated_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_token_scores_token_time ON token_scores (token_id, calculated_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_token_scores_tournament_time ON token_scores (tournament_id, token_id, calculated_at)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_token_scores_tournament_time")
    op.execute("DROP INDEX IF EXISTS idx_token_scores_token_time")
    op.execute("DROP INDEX IF EXISTS idx_token_scores_calculated_at")
    op.execute("DROP TABLE IF EXISTS token_scores")
