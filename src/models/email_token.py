# --- FILE: src/models/email_token.py ---
"""
One-time links from e-mails (task 17.5): e-mail confirmation and password reset. Only the SHA-256 of the token is in the
database:
a table leak gives no working links. The link is valid until expires_at and only once (used_at).
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.models.base import Base


class EmailToken(Base):
    """
    A one-time link from an e-mail - address confirmation or password reset. The token hash, the expiry and the mark
    of use are stored.
    """
    __tablename__ = "email_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)  # verify | reset
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # For confirmation - the address being confirmed; for reset - the address the e-mail was sent to.
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
