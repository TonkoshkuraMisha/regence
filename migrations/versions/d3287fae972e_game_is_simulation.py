# --- FILE: migrations/versions/d3287fae972e_game_is_simulation.py ---

"""game_is_simulation

A mark for bot-vs-bot games played by the server in a tournament (task 15.2): such games do not go into the archive and
profile statistics; the time the worker picked up a tournament game (protection against double counting).

Revision ID: d3287fae972e
Revises: a5db857ccde4
Create Date: 2026-11-13 17:21:09.980998

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d3287fae972e"
down_revision: str | Sequence[str] | None = "a5db857ccde4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("games", sa.Column("is_simulation", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("tournament_games", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("tournament_games", "started_at")
    op.drop_column("games", "is_simulation")
