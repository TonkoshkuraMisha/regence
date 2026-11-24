"""
The weekly tournament against legends (task 26.1, src/services/weekly_legends.py): one row per counted game - a player, a
week (its UTC Monday), the legend (a historical bot id) and the result in half-points. A legend can be played once a week,
so the triple is unique. forfeit is the reason a game was counted as a loss (a hint, a takeback, a wrong time control, an
abandoned game); game_id points to the saved game in the archive (empty for an abandoned one).
"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class WeeklyLegendGame(Base):
    """A counted game of the weekly tournament against legends; what the columns mean - in the module description."""
    __tablename__ = "weekly_legend_games"
    __table_args__ = (UniqueConstraint("week", "user_id", "bot_id", name="uq_weekly_legend_games_week_user_bot"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    week: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    bot_id: Mapped[str] = mapped_column(String(32), nullable=False)
    half_points: Mapped[int] = mapped_column(Integer, nullable=False)
    forfeit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    game_id: Mapped[int | None] = mapped_column(ForeignKey("games.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
