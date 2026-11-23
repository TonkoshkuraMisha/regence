# --- FILE: src/models/lesson.py ---
"""
School lesson progress (task 14.1). The lessons themselves are client data files (frontend/src/content/lessons/*.json):
the lesson texts in three languages live next to the other interface texts. The server stores only how far the player
got in a lesson and how they passed the quiz questions.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class LessonProgress(Base):
    """
    A player's progress in one lesson: how far they got and how they answered the quiz questions. One row per "player -
    lesson" pair.
    """
    __tablename__ = "lesson_progress"
    __table_args__ = (UniqueConstraint("user_id", "lesson_id", name="uq_lesson_progress_user_lesson"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    lesson_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # The furthest passed step (a number from zero): "Continue" returns to it.
    step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    steps_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The best result of the lesson's quiz questions (correct on the first try) out of exam_total.
    exam_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exam_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )
