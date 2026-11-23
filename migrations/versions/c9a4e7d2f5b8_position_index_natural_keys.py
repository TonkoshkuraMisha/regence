"""position index natural keys (audit 29.1, finding 1): composite primary keys instead of surrogate id

Revision ID: c9a4e7d2f5b8
Revises: 59c61fc287c2
Create Date: 2026-11-18 13:00:00.000000

position_stats: key (position_hash, move_uci), position_games: key (position_hash, game_id). Both used to have
a surrogate id (nobody used it) plus a unique index on the same pairs - now the pair itself is the primary
key, the extra column and index go away. Behaviour does not change: index inserts use ON CONFLICT on the same columns.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c9a4e7d2f5b8'
down_revision: str | Sequence[str] | None = '59c61fc287c2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, key columns, name of the former unique constraint)
TABLES = (
    ('position_stats', ('position_hash', 'move_uci'), 'uq_position_stats_move'),
    ('position_games', ('position_hash', 'game_id'), 'uq_position_games_game'),
)


def upgrade() -> None:
    """Upgrade schema."""
    for table, columns, unique in TABLES:
        op.drop_constraint(unique, table, type_='unique')
        op.drop_column(table, 'id')  # the former primary key goes away together with it
        op.create_primary_key(f'{table}_pkey', table, list(columns))


def downgrade() -> None:
    """Downgrade schema: the surrogate id and the unique constraints come back."""
    for table, columns, unique in reversed(TABLES):
        op.drop_constraint(f'{table}_pkey', table, type_='primary')
        op.execute(f'ALTER TABLE {table} ADD COLUMN id SERIAL PRIMARY KEY')
        op.create_unique_constraint(unique, table, list(columns))
