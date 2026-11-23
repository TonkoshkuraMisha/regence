"""Position index of library games for the opening explorer examples (task 8b)

Revision ID: a8d3f6c2e5b7
Revises: f2a7c4e9b1d6
Create Date: 2026-11-18 18:00:00.000000

Games from public library collections are shown under a position in the opening reference as examples. For this there is
a dedicated table of positions position_library_games (like position_games for site and archive games) and a flag
library_games.positions_indexed. Library games are not part of the move statistics (position_stats): many of them are also in
the champions archive. The table is filled by the library import, and already loaded games by scripts/build_position_index.py
--library. The downgrade drops the table and the flag; the index is rebuilt by the same script.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a8d3f6c2e5b7'
down_revision: str | Sequence[str] | None = 'f2a7c4e9b1d6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create position_library_games and the indexed flag on library games."""
    op.create_table(
        'position_library_games',
        sa.Column('position_hash', sa.BigInteger(), nullable=False),
        sa.Column('library_game_id', sa.Integer(), nullable=False),
        sa.Column('ply', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['library_game_id'], ['library_games.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('position_hash', 'library_game_id'),
    )
    op.create_index(op.f('ix_position_library_games_library_game_id'), 'position_library_games', ['library_game_id'],
                    unique=False)
    op.add_column('library_games', sa.Column('positions_indexed', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    """Drop the table and the flag."""
    op.drop_column('library_games', 'positions_indexed')
    op.drop_index(op.f('ix_position_library_games_library_game_id'), table_name='position_library_games')
    op.drop_table('position_library_games')
