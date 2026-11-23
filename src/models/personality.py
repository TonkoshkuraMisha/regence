# --- FILE: src/models/personality.py ---
"""
Opponents built by players in the workshop (the bot_personalities table): a name and character settings. Name rules and
limits - src/api/personalities.py, how a play style is obtained from the settings - src/services/bots/personality.py.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class BotPersonality(Base):
    """An opponent built by a player in the workshop: a name and BotPersonalityConfig in JSON."""

    __tablename__ = "bot_personalities"
    __table_args__ = (UniqueConstraint("owner_id", "name_key", name="uq_bot_personalities_owner_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(30), nullable=False)
    # The name is case-insensitively unique within an owner.
    name_key: Mapped[str] = mapped_column(String(30), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )
