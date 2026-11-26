# --- FILE: src/models/social.py ---
"""
Players and notifications (task 17.1): follows (a mutual follow means "friends") and the notification centre. Notification
texts
are assembled by the client from the kind code (kind) and parameters (payload) - the server stores no human strings.

This same file has the communication tables (tasks 30.1-30.3): direct messages and the block list
(src/services/direct_messages.py), feed posts, comments and "like" marks (src/services/feed.py),
hidden conversations. The texts of messages and posts are player input; what the insult filter held (held) waits for a
moderator's decision (src/services/civility.py, src/services/moderation.py).
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class Follow(Base):
    """One player's follow of another. A mutual follow means "friends"."""
    __tablename__ = "follows"
    __table_args__ = (UniqueConstraint("follower_id", "followee_id", name="uq_follow_pair"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    follower_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    followee_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    """
    A notification to a player: a kind (kind) and parameters (payload) from which the client assembles the text in its
    language; read_at -
    when it was read.
    """
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # challenge | rematch | tournament_round | report_answer | workout_reminder | post_comment | arena_reminder |
    # arena_podium | legends_week
    # (the list is notifications.KINDS; the client gets the latest notifications.KEEP, old ones are not deleted from the
    # database).
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DirectMessage(Base):
    """A direct message (task 30.1). The text is player input; the attachment is a card {kind, ref, ...snapshot} without
    interface
    strings. pair_key = "smaller_id:larger_id" - the conversation of two players by one index."""

    __tablename__ = "direct_messages"
    __table_args__ = (Index("ix_direct_messages_pair_id", "pair_key", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pair_key: Mapped[str] = mapped_column(String(24))
    sender_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    recipient_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(String(1000), default="", server_default="")
    attachment: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Held by the insult filter (task 30.3): visible only to the sender until the moderator decides.
    held: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)


class Block(Base):
    """The block list (task 30.1): blocker receives no messages from blocked and does not write to them either."""

    __tablename__ = "blocks"
    __table_args__ = (UniqueConstraint("blocker_id", "blocked_id", name="uq_block_pair"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    blocker_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    blocked_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Post(Base):
    """A feed post (task 30.2): the player's text and/or a card (src/services/attachments.py). hidden_at -
    hidden by a moderator (task 30.3): visible to the author, not in feeds."""

    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(String(2000), default="", server_default="")
    attachment: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    held: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)


class PostComment(Base):
    """A comment on a feed post; the text is player input."""
    __tablename__ = "post_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    held: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)


class PostLike(Base):
    """A "like" mark: one player - one mark per post."""
    __tablename__ = "post_likes"
    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uq_post_like"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HiddenConversation(Base):
    """"Hide an interlocutor" (task 30.3): the conversation is not shown in my list until they write again
    (a new message with an id greater than up_to_id). Without blocking: they can still write."""

    __tablename__ = "hidden_conversations"
    __table_args__ = (UniqueConstraint("user_id", "other_id", name="uq_hidden_conversation"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    other_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    up_to_id: Mapped[int] = mapped_column(Integer)
