# --- FILE: src/models/collection.py ---
"""
The archive's "fun collections" (task 16.3): the shortest games, the most checks, etc. They are computed in advance
by the script scripts/build_collections.py (rules - src/services/collections.py), here are the ready places in the collections.
"""

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class CollectionEntry(Base):
    """
    A place of an archive game in one of the "fun collections": the collection code, the place and the indicator by which the
    game
    got into it. The whole table is replaced by scripts/build_collections.py.
    """
    __tablename__ = "collection_entries"
    __table_args__ = (UniqueConstraint("collection", "rank", name="uq_collection_rank"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    collection: Mapped[str] = mapped_column(String(32), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    # The collection indicator: plies, checks, consecutive captures, promotions, passed pawns.
    value: Mapped[int] = mapped_column(Integer)
