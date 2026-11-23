# --- FILE: migrations/versions/a7c9e1f3b5d2_puzzles.py ---

"""puzzles

Puzzle database (task 13.1): puzzles, their themes from the registry, solve attempts and the solver rating on the user.
The puzzles themselves are loaded by scripts/import_puzzles.py from data/puzzles/ - the migration only creates the tables.

Revision ID: a7c9e1f3b5d2
Revises: f2b8d4e6a1c3
Create Date: 2026-11-14 02:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7c9e1f3b5d2"
down_revision: str | Sequence[str] | None = "f2b8d4e6a1c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "puzzles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("source_id", sa.String(20), nullable=False),
        sa.Column("fen", sa.String(100), nullable=False),
        sa.Column("moves", sa.String(400), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("rating_deviation", sa.Integer(), nullable=False, server_default="75"),
        sa.Column("popularity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("plays", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_tags", sa.String(300), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source", "source_id", name="uq_puzzles_source"),
    )
    op.create_index("ix_puzzles_rating", "puzzles", ["rating"])
    op.create_table(
        "puzzle_themes",
        sa.Column("puzzle_id", sa.Integer(), sa.ForeignKey("puzzles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("theme", sa.String(40), primary_key=True),
    )
    op.create_index("ix_puzzle_themes_theme", "puzzle_themes", ["theme"])
    op.create_table(
        "puzzle_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("puzzle_id", sa.Integer(), sa.ForeignKey("puzzles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("solved", sa.Boolean(), nullable=False),
        sa.Column("hints_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rating_before", sa.Integer(), nullable=False),
        sa.Column("rating_after", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_puzzle_attempts_user_id", "puzzle_attempts", ["user_id"])
    op.create_index("ix_puzzle_attempts_puzzle_id", "puzzle_attempts", ["puzzle_id"])
    op.create_index("ix_puzzle_attempts_created_at", "puzzle_attempts", ["created_at"])
    op.add_column("users", sa.Column("puzzle_rating", sa.Integer(), nullable=False, server_default="1500"))
    op.add_column("users", sa.Column("puzzle_games", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("users", "puzzle_games")
    op.drop_column("users", "puzzle_rating")
    op.drop_index("ix_puzzle_attempts_created_at", table_name="puzzle_attempts")
    op.drop_index("ix_puzzle_attempts_puzzle_id", table_name="puzzle_attempts")
    op.drop_index("ix_puzzle_attempts_user_id", table_name="puzzle_attempts")
    op.drop_table("puzzle_attempts")
    op.drop_index("ix_puzzle_themes_theme", table_name="puzzle_themes")
    op.drop_table("puzzle_themes")
    op.drop_index("ix_puzzles_rating", table_name="puzzles")
    op.drop_table("puzzles")
