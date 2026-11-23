# --- FILE: src/models/ladder.py ---
"""
The club ladder (tasks 10.4, 21.4, task 7 of the owner's plan of 18.11): which rungs the player has beaten. A rung is the
opponent's
key ("morphy", "archetype:rusher"), not a number in a list: new opponents are placed in the ladder by strength, and players'
progress does not shift from that. The current rung is computed by src/services/ladder.py from this set.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class LadderBeaten(Base):
    """A beaten rung: the player defeated this opponent when it was their current rung."""
    __tablename__ = "ladder_beaten"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    # The rung key (src/services/ladder.Rung.key): the id of a historical bot or "archetype:<id>".
    rung_key: Mapped[str] = mapped_column(String(48), primary_key=True)
    beaten_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
