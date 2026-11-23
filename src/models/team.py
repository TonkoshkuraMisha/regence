# --- FILE: src/models/team.py ---
"""
Teams and the season league (task 17.2): a player belongs to at most one team. League points are counted from played
rated games between players of different teams (src/services/league.py) - there is no separate results table.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class Team(Base):
    """A season league team: a name and an owner."""
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The team name is player text (not an interface string); unique case-insensitively (checked by the service).
    name: Mapped[str] = mapped_column(String(30), unique=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TeamMember(Base):
    """A team member. A player belongs to at most one team."""
    __tablename__ = "team_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    # One player - one team.
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
