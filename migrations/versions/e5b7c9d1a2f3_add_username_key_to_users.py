# --- FILE: migrations/versions/e5b7c9d1a2f3_add_username_key_to_users.py ---

"""add_username_key_to_users

A normalised name (casefold) for accounts with a password: case-insensitive uniqueness and
login in any case. It stays NULL for archived players from PGN and for bots - their names from
game headers can legitimately differ only by case.

Revision ID: e5b7c9d1a2f3
Revises: d9f4a1b2c3e4
Create Date: 2026-11-10 18:00:00.000000

"""
import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5b7c9d1a2f3"
down_revision: str | Sequence[str] | None = "d9f4a1b2c3e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

# Markers instead of a password hash for accounts that cannot be logged into.
NO_LOGIN_MARKERS = ("!historical_archive_no_login!", "!historical_bot_no_login!")


def upgrade() -> None:
    op.add_column("users", sa.Column("username_key", sa.String(length=50), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, username, hashed_password FROM users ORDER BY id")
    ).fetchall()

    # The key is computed in Python (casefold), not with lower() in SQL: lower() in PostgreSQL with the C locale
    # and in SQLite does not lowercase Cyrillic. When keys collide the key goes to the oldest
    # account; the rest stay without a key and still log in under the exact name.
    taken: dict[str, int] = {}
    for user_id, username, hashed_password in rows:
        if hashed_password in NO_LOGIN_MARKERS or not username:
            continue
        key = username.strip().casefold()[:50]
        if key in taken:
            logger.warning(
                "users.username_key: '%s' (id=%s) differs only in case from id=%s; left without key",
                username, user_id, taken[key],
            )
            continue
        taken[key] = user_id
        bind.execute(
            sa.text("UPDATE users SET username_key = :key WHERE id = :id"),
            {"key": key, "id": user_id},
        )

    op.create_index(op.f("ix_users_username_key"), "users", ["username_key"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_username_key"), table_name="users")
    op.drop_column("users", "username_key")
