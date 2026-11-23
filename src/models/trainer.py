# --- FILE: src/models/trainer.py ---
"""
Trainer results (task 19.1): trainer -> level -> attempt -> result (points, time, mistakes). Personal records and
the chart are built from this table (src/api/trainers.py). The trainers themselves run on the client.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class TrainerResult(Base):
    """The result of one attempt in a trainer: the trainer, level, points, time, mistakes."""
    __tablename__ = "trainer_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    trainer: Mapped[str] = mapped_column(String(32), index=True)
    level: Mapped[int] = mapped_column(Integer)
    score: Mapped[int] = mapped_column(Integer)
    time_ms: Mapped[int] = mapped_column(Integer)
    mistakes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class ExamResult(Base):
    """
    The result of a diagnostic exam (task 22.0): a theme catalogue section (or "endgame" - the endgame exam), correct
    answers out of how many, the strength estimate from the answers. The starting data of the skill map (22.1); it does not
    change the game rating.
    """

    __tablename__ = "exam_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    section: Mapped[str] = mapped_column(String(10), index=True)
    correct: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    estimate: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
