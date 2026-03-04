"""add_alpha_test_access_table

Revision ID: c386c065fd27
Revises: 5559a247c5a8
Create Date: 2026-01-23 10:46:32.440647

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c386c065fd27'
down_revision: Union[str, None] = '5559a247c5a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS alpha_test_access (
            id SERIAL NOT NULL PRIMARY KEY,
            wallet_address VARCHAR(42) NOT NULL UNIQUE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS alpha_test_access")
