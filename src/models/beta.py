# --- FILE: src/models/beta.py ---
"""
The beta programme (task 24.4): invite codes for closed registration and "Report a problem" messages.

Invites are created and revoked by a moderator; uses is how many people registered with the code (and the basis of the limit).
A problem report can also come from a guest (user_id is empty); to the player's text the server and the client attach
context: the page, the app version, the language and the screen size.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, one_of

# Statuses of a player's feedback (src/services/beta.py, FEEDBACK_STATUSES).
FEEDBACK_STATUSES = ("new", "in_progress", "done", "rejected")


class Invite(Base):
    """
    An invite code for closed registration: usage limit, expiry, revocation; uses is how many people have already
    registered with the code.
    """
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    # The moderator's own note: to whom the code was given (human input, not an interface string).
    note: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Empty - no limit.
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uses: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Feedback(Base):
    """
    A "Report a problem" message: the text of a player or a guest, context (page, version, language, screen size) and the
    status
    of moderator review.
    """
    __tablename__ = "feedback"
    __table_args__ = (one_of("feedback", "status", FEEDBACK_STATUSES),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    message: Mapped[str] = mapped_column(String(2000))
    # Context: the page path, the app version, the interface language, the screen size ("1280x720").
    page: Mapped[str | None] = mapped_column(String(200), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    screen: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # new | in_progress | done | rejected
    status: Mapped[str] = mapped_column(String(16), default="new", server_default="new", index=True)
    moderator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
