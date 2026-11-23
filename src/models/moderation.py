# --- FILE: src/models/moderation.py ---
"""
Moderation (task 17.4): player reports (about a player or a chat message), automatic requests to review the unfair-play flag
and appeals; since task 30.3 also reports about a specific text (a direct message, a post,
a comment) and texts held by the insult filter; since 17.7 - suggestions to fix a translation. The queue is
worked by a moderator (users.is_moderator), the decision is a code (src/services/moderation.py).
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, one_of

# Kinds of requests to a moderator (src/services/moderation.py, civility.py).
REPORT_KINDS = ("player", "message", "cheat_review", "appeal", "translation", "content", "held")
# Reasons: those chosen by the player (moderation.REASONS) and "auto" - a request from automation.
REPORT_REASONS = ("cheating", "abuse", "spam", "other", "auto")
REPORT_STATUSES = ("open", "resolved")
# Moderator decisions (moderation.ACTIONS); NULL - the request has not been reviewed yet.
REPORT_ACTIONS = ("dismiss", "warn", "chat_ban", "mark_cheater", "clear_cheater", "accept", "hide", "release")


class Report(Base):
    """
    A request in the moderator's queue: a player report, an automatic unfair-play flag check, an appeal or
    a held text. The decision is recorded as a code.
    """
    __tablename__ = "reports"
    __table_args__ = (
        one_of("reports", "kind", REPORT_KINDS),
        one_of("reports", "reason", REPORT_REASONS),
        one_of("reports", "status", REPORT_STATUSES),
        one_of("reports", "action", REPORT_ACTIONS),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # player | message | cheat_review (automatic on a flag) | appeal (an appeal against the flag) |
    # translation (a suggestion to fix an interface text, task 17.7) | content (a report about a direct message,
    # post or comment, task 30.3) | held (the text is held by the insult filter, src/services/civility.py)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    reporter_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    target_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # cheating | abuse | spam | other | auto
    reason: Mapped[str] = mapped_column(String(16))
    # The reporter's text and a copy of a chat message (human input - for the moderator, not interface strings).
    comment: Mapped[str | None] = mapped_column(String(300), nullable=True)
    message_text: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # For translation: the catalogue "language:key" and the page where it was suggested (context). For content and held subject
    # is
    # a reference to the text: "dm:id", "post:id" or "comment:id".
    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    context: Mapped[str | None] = mapped_column(String(200), nullable=True)
    game_id: Mapped[int | None] = mapped_column(ForeignKey("games.id", ondelete="SET NULL"), nullable=True, index=True)
    # open | resolved
    status: Mapped[str] = mapped_column(String(16), default="open", server_default="open", index=True)
    # The decision (moderation.ACTIONS): dismiss | warn | chat_ban | mark_cheater | clear_cheater | accept (for
    # translation) | hide (remove the text) | release (release the held text)
    action: Mapped[str | None] = mapped_column(String(16), nullable=True)
    moderator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
