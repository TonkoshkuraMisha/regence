"""library game themes

Revision ID: e6a9c2f4b8d1
Revises: d5f8b1c3e7a2
Create Date: 2026-11-27 22:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e6a9c2f4b8d1'
down_revision: str | Sequence[str] | None = 'd5f8b1c3e7a2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('library_games', sa.Column('themes', sa.String(length=200), server_default='', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('library_games', 'themes')
