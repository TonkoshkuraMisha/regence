"""game hourglass

A game with an "hourglass" (handicap, task 21.1): the flag is needed so that after the state is restored from the DB the clock
keeps running by the same rules.

Revision ID: e4b9c2d7a1f3
Revises: d3a8f1c6e2b7
Create Date: 2026-11-20 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e4b9c2d7a1f3'
down_revision: str | Sequence[str] | None = 'e5b1c9a7d3f2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('games', sa.Column('hourglass', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('games', 'hourglass')
