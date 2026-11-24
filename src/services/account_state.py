# --- FILE: src/services/account_state.py ---
"""
Whether an account is open (task 23.1): one rule for every place that shows a player to others or lets others reach them.

An account is closed when it is deleted (users.deleted_at, already anonymised) or waiting for deletion
(users.deletion_requested_at, the grace period of src/services/account.py). A closed account has no public profile, is not
in search, leaderboards or feeds, and cannot be written to. The data itself is untouched until the purge, so logging in during
the grace period restores everything.

is_closed answers for a loaded player, open_account gives the same rule as SQL conditions for queries.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import ColumnElement

from src.models.user import User


def is_closed(user: User | None) -> bool:
    """Deleted or waiting for deletion; a missing player counts as closed."""
    return user is None or user.deleted_at is not None or user.deletion_requested_at is not None


def open_account() -> tuple[ColumnElement[bool], ...]:
    """SQL conditions of an open account: not deleted and not waiting for deletion."""
    return User.deleted_at.is_(None), User.deletion_requested_at.is_(None)


def delete_after(requested_at: datetime, grace_days: int) -> datetime:
    """The moment after which a requested deletion is carried out (the end of the grace period)."""
    return requested_at + timedelta(days=grace_days)
