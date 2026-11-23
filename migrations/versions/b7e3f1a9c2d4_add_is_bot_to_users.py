# --- FILE: migrations/versions/b7e3f1a9c2d4_add_is_bot_to_users.py ---

"""add_is_bot_to_users

Historical bots (playable AI opponents) and archived historical players (games from
PGN archives, can be viewed but not played) used to be recognised by a service marker in
hashed_password. An explicit column is more reliable and allows removing them from the leaderboard with a single
condition instead of guessing by the password string in every query.

Revision ID: b7e3f1a9c2d4
Revises: f6c8d0e2b3a4
Create Date: 2026-11-11 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e3f1a9c2d4"
down_revision: str | Sequence[str] | None = "f6c8d0e2b3a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The same markers as in src/api/bots.py (BOT_PASSWORD_MARKER) and src/db/seed.py.
NO_LOGIN_MARKERS = ("!historical_bot_no_login!", "!historical_archive_no_login!")


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_bot", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    bind = op.get_bind()
    bind.execute(
        sa.text("UPDATE users SET is_bot = true WHERE hashed_password IN :markers").bindparams(
            sa.bindparam("markers", expanding=True)
        ),
        {"markers": list(NO_LOGIN_MARKERS)},
    )


def downgrade() -> None:
    op.drop_column("users", "is_bot")
