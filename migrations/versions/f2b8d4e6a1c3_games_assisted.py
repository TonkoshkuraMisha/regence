# --- FILE: migrations/versions/f2b8d4e6a1c3_games_assisted.py ---

"""games_assisted

Play with a mentor (task 11.3): a game in which the player used advice or move checking is marked
as a training game (rule 2 of Part II).

Revision ID: f2b8d4e6a1c3
Revises: e1a7c3d9b5f2
Create Date: 2026-11-13 18:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2b8d4e6a1c3"
down_revision: str | Sequence[str] | None = "e1a7c3d9b5f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("games", sa.Column("assisted", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    op.drop_column("games", "assisted")
