"""library beautiful tag

Revision ID: b8d2f4a6c1e3
Revises: a7c3e9b1d5f2
Create Date: 2026-11-22 18:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b8d2f4a6c1e3'
down_revision: str | Sequence[str] | None = 'a7c3e9b1d5f2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('library_games', sa.Column('beautiful', sa.Boolean(), server_default='false', nullable=False))
    op.create_index(op.f('ix_library_games_beautiful'), 'library_games', ['beautiful'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_library_games_beautiful'), table_name='library_games')
    op.drop_column('library_games', 'beautiful')
