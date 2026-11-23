# --- FILE: src/models/achievement.py ---
"""A player's unlocked achievements (task 17.6): the code and date; the conditions are in src/services/achievements.py."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class UserAchievement(Base):
    """
    An achievement unlocked by a player: the achievement code and the date. One achievement is recorded once; the conditions
    are checked by
    src/services/achievements.py.
    """
    __tablename__ = "user_achievements"
    __table_args__ = (UniqueConstraint("user_id", "code", name="uq_user_achievement"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(32))
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
