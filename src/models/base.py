"""
The base class of SQLAlchemy models: all tables inherit from it (src/models/*.py), and the shared one_of helper for
enum constraints.
"""

from collections.abc import Iterable

from sqlalchemy import CheckConstraint
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    The common ancestor of all models: its metadata collects the tables from which Alembic builds migrations.
    """
    pass


def one_of(table: str, column: str, values: Iterable[str]) -> CheckConstraint:
    """
    A CHECK constraint "the column value is one of values" named ck_<table>_<column> (database audit 29.1,
    finding 3): a non-existent status will be written neither by a code error nor by a manual edit. NULL passes the constraint
    -
    mandatory-ness is set by the column's nullable. The set of values is a tuple next to the column in the model; if the same
    set
    exists in a service, their equality is checked by tests/test_db_integrity.py. A new value is a tuple edit and a migration
    (Alembic does not find such constraints itself - the migration is written by hand, following 59c61fc287c2).
    """
    listed = ", ".join(f"'{value}'" for value in values)
    return CheckConstraint(f"{column} IN ({listed})", name=f"ck_{table}_{column}")
