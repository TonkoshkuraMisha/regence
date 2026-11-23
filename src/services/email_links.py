# --- FILE: src/services/email_links.py ---
"""
Player e-mail and password reset (task 17.5).

* Address confirmation: the player enters an address (with the password), a one-time link is sent to it; the address is
  written to
  the profile only via the link. Until confirmed it is not recorded anywhere, so someone else's address cannot be claimed
  this way.
* Password reset: a one-time link valid for an hour is sent to a confirmed address. The response to the request is always the
  same --
  it does not reveal whether such an address exists. A new password revokes all tokens and other reset links.

Where it is stored: links -- the email_tokens table (purpose, address, expiry, used mark); the database holds only the
sha256 of the link secret, the secret itself exists only in the e-mail. Lifetimes are the settings EMAIL_VERIFY_TTL_S (a day)
and
PASSWORD_RESET_TTL_S (an hour), the site address in the link is PUBLIC_BASE_URL. E-mails are composed and sent by
src/services/mailer.py (without SMTP_HOST the e-mail is not sent but written to the log). Request limits for e-mails (per
address and per
IP, the RATE_LIMIT_EMAIL_* settings) are in the routes of src/api/account.py.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.errors import ApiError
from src.core.security import get_password_hash
from src.models.email_token import EmailToken
from src.models.user import User
from src.services import mailer

# Link purpose (email_tokens.purpose): address confirmation and password reset. A link of one purpose is not
# accepted where the other is expected.
VERIFY = "verify"
RESET = "reset"


def normalize(email: str) -> str:
    """The address in the form used for comparison and storage: trimmed of surrounding whitespace, lower case."""
    return email.strip().lower()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def _issue(db: AsyncSession, user: User, purpose: str, email: str, ttl_s: int) -> str:
    """
    A new one-time link: the secret's hash and expiry are written to the database (with commit), the secret itself is
    returned for the e-mail.
    """
    token = secrets.token_urlsafe(32)
    db.add(EmailToken(user_id=user.id, purpose=purpose, token_hash=_hash(token), email=email,
                      expires_at=_now() + timedelta(seconds=ttl_s)))
    await db.commit()
    return token


async def _taken(db: AsyncSession, email: str, user_id: int) -> bool:
    """Whether this address is recorded (case-insensitively) in another player's profile."""
    other = await db.scalar(select(User.id).where(func.lower(User.email) == email, User.id != user_id))
    return other is not None


async def request_verification(db: AsyncSession, user: User, email: str, language: str) -> None:
    """
    An e-mail with a one-time link for address confirmation. An address already confirmed by another player -- refusal
    email_taken.
    """
    email = normalize(email)
    if await _taken(db, email, user.id):
        raise ApiError(409, "email_taken")
    token = await _issue(db, user, VERIFY, email, settings.EMAIL_VERIFY_TTL_S)
    subject, body = mailer.render(
        "verify", language, username=user.username, hours=settings.EMAIL_VERIFY_TTL_S // 3600,
        link=f"{settings.PUBLIC_BASE_URL.rstrip('/')}/verify-email?token={token}",
    )
    await mailer.send(email, subject, body)


async def _consume(db: AsyncSession, token: str, purpose: str) -> EmailToken:
    """
    Finds a link by the secret's hash and purpose and marks it used (without commit -- the caller does that).
    An unknown, already used or expired link -- refusal 400 email_link_invalid.
    """
    row = await db.scalar(select(EmailToken).where(EmailToken.token_hash == _hash(token), EmailToken.purpose == purpose))
    if row is None or row.used_at is not None or _aware(row.expires_at) < _now():
        raise ApiError(400, "email_link_invalid")
    row.used_at = _now()
    return row


async def confirm_verification(db: AsyncSession, token: str) -> User:
    """
    Following the link from the e-mail: the address is written to the profile. An invalid, expired or already used
    link -- refusal. If another player confirmed the address before the link was followed -- refusal email_taken.
    """
    row = await _consume(db, token, VERIFY)
    user = await db.get(User, row.user_id)
    if user is None or user.deleted_at is not None:
        raise ApiError(400, "email_link_invalid")
    if await _taken(db, row.email, user.id):
        raise ApiError(409, "email_taken")
    user.email = row.email
    await db.commit()
    return user


async def request_reset(db: AsyncSession, email: str, language: str) -> None:
    """An e-mail with a reset link if the address is confirmed on a live account; otherwise nothing (and the same response)."""
    email = normalize(email)
    user = await db.scalar(select(User).where(func.lower(User.email) == email, User.deleted_at.is_(None)))
    if user is None:
        return
    token = await _issue(db, user, RESET, email, settings.PASSWORD_RESET_TTL_S)
    subject, body = mailer.render(
        "reset", language, username=user.username, hours=max(1, settings.PASSWORD_RESET_TTL_S // 3600),
        link=f"{settings.PUBLIC_BASE_URL.rstrip('/')}/reset-password?token={token}",
    )
    await mailer.send(email, subject, body)


async def confirm_reset(db: AsyncSession, token: str, new_password: str) -> User:
    """
    A new password via the link from the e-mail: the hash is replaced, all the player's tokens and other reset links are
    revoked, open
    connections are closed.
    """
    row = await _consume(db, token, RESET)
    user = await db.get(User, row.user_id)
    if user is None or user.deleted_at is not None:
        raise ApiError(400, "email_link_invalid")
    user.hashed_password = get_password_hash(new_password)
    user.token_version = (user.token_version or 0) + 1
    # The player's other reset links are no longer valid.
    await db.execute(update(EmailToken).where(
        EmailToken.user_id == user.id, EmailToken.purpose == RESET, EmailToken.used_at.is_(None),
    ).values(used_at=_now()))
    await db.commit()
    from src.services.connection_manager import manager

    await manager.revoke_sessions(user.id)
    return user
