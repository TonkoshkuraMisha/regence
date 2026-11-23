# --- FILE: src/models/study.py ---
"""Club materials (task 17.3): a host's session saved as a lesson in the school format (task 14.1)."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class StudyMaterial(Base):
    """A club material: a session saved by the host as a lesson in the school format."""
    __tablename__ = "study_materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(80))
    # A lesson in the format of frontend/src/content/lessons/format.ts (steps text/demo/find_move/choice).
    lesson: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
