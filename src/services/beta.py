# --- FILE: src/services/beta.py ---
"""
Beta programme (task 24.4).

* Invitations. A code is created by a moderator: with a usage limit and an expiry (both optional), revocation —
  at any moment. A code is accepted while it is not revoked, not expired and not used up. The deduction is a single UPDATE with
  a condition,
  in the same transaction as account creation: two simultaneous requests cannot exceed the limit, and a failed
  registration does not spend the code.
* "Report a problem". The text of a player (or guest) with context: page, app version, language, screen size.
  A moderator queue with statuses new → in_progress → done | rejected.
* Summary for a period (scripts/feedback_digest.py): how many arrived, how they were handled, on which pages, a list.
"""

import secrets
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.errors import DomainError
from src.models.beta import Feedback, Invite
from src.models.user import User

# Without lookalike characters (0/O, 1/I/L): the code is dictated and retyped by hand.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
# Length of a generated code and the maximum code length accepted on input (the excess is dropped in normalize_code).
CODE_LENGTH = 10
MAX_CODE_LENGTH = 32
# A player's personal invitation ("invite a friend", task 26.2): a code mark and a cap on registrations through it — protection
# against
# handing one code to thousands of accounts (more — only a moderator code).
FRIEND_NOTE = "friend"
FRIEND_MAX_USES = 50
# Upper bounds of the usage limit and the code's lifetime; they are checked by the request schema in src/api/beta.py.
MAX_USES = 100_000
MAX_EXPIRES_DAYS = 365

# Statuses of a problem report; OPEN_STATUSES are the unhandled ones (the default moderator queue and the remainder in the
# summary).
FEEDBACK_STATUSES = ("new", "in_progress", "done", "rejected")
OPEN_STATUSES = ("new", "in_progress")
# Report text length in characters: longer is truncated, shorter is refused with feedback_invalid.
MESSAGE_MAX = 2000
MESSAGE_MIN = 5
# How many reports the moderator queue returns per request.
FEEDBACK_PAGE_SIZE = 100
# Interface languages; any other language value is not stored in a report.
LANGUAGES = ("en", "uk")


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


def _iso(value: datetime | None) -> str | None:
    value = _aware(value)
    return value.isoformat() if value is not None else None


def _moderator(user: User) -> None:
    if not user.is_moderator:
        raise DomainError("moderator_only")


def community_url() -> str | None:
    """Community channel link from the server settings; anything other than an http(s) address does not count as a link."""
    url = settings.COMMUNITY_URL.strip()
    return url if url.startswith(("https://", "http://")) else None


# --- invitations ---------------------------------------------------------------------------------------------------

def normalize_code(raw: str | None) -> str:
    """The code as stored: without spaces, upper case, no longer than MAX_CODE_LENGTH characters."""
    return "".join((raw or "").split()).upper()[:MAX_CODE_LENGTH]


def invite_state(invite: Invite, now: datetime | None = None) -> str:
    """active | revoked | expired | used_up; with several reasons at once — the first of them in this check order."""
    now = now or _now()
    if invite.revoked_at is not None:
        return "revoked"
    expires = _aware(invite.expires_at)
    if expires is not None and expires <= now:
        return "expired"
    if invite.max_uses is not None and invite.uses >= invite.max_uses:
        return "used_up"
    return "active"


def _invite_view(invite: Invite, now: datetime) -> dict:
    return {
        "id": invite.id, "code": invite.code, "note": invite.note, "max_uses": invite.max_uses, "uses": invite.uses,
        "expires_at": _iso(invite.expires_at), "revoked_at": _iso(invite.revoked_at),
        "created_at": _iso(invite.created_at), "state": invite_state(invite, now),
    }


async def create_invite(db: AsyncSession, moderator: User, note: str | None, max_uses: int | None,
                        expires_in_days: int | None) -> dict:
    """
    New code: CODE_LENGTH random characters from CODE_ALPHABET. The bounds of max_uses and expires_in_days are checked by the
    request
    schema (src/api/beta.py); an empty value means no limit or no expiry. The note mark is up to 100 characters.
    """
    _moderator(moderator)
    now = _now()
    invite = Invite(
        code="".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH)),
        note=" ".join((note or "").split())[:100] or None, max_uses=max_uses,
        expires_at=now + timedelta(days=expires_in_days) if expires_in_days else None, created_by=moderator.id,
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    return _invite_view(invite, now)


async def my_invite(db: AsyncSession, user: User) -> dict:
    """
    The player's personal code for inviting friends (created on first access, the same afterwards): the code, how many people
    registered through it and its state. The same Invite as the moderator's — registration and the counter are shared.
    """
    invite = await db.scalar(select(Invite).where(Invite.created_by == user.id, Invite.note == FRIEND_NOTE))
    if invite is None:
        invite = Invite(
            code="".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH)),
            note=FRIEND_NOTE, max_uses=FRIEND_MAX_USES, created_by=user.id,
        )
        db.add(invite)
        await db.commit()
        await db.refresh(invite)
    return {"code": invite.code, "uses": invite.uses, "max_uses": invite.max_uses, "state": invite_state(invite)}


async def list_invites(db: AsyncSession, moderator: User) -> list[dict]:
    """All invitations, newest first: how many people came through each and whether it is valid."""
    _moderator(moderator)
    now = _now()
    rows = (await db.execute(select(Invite).order_by(Invite.created_at.desc(), Invite.id.desc()))).scalars().all()
    return [_invite_view(invite, now) for invite in rows]


async def revoke_invite(db: AsyncSession, moderator: User, invite_id: int) -> dict:
    """Revocation of an invitation code by a moderator: the code stops being accepted. Revoking again changes nothing."""
    _moderator(moderator)
    invite = await db.get(Invite, invite_id)
    if invite is None:
        raise DomainError("beta_invite_not_found")
    now = _now()
    if invite.revoked_at is None:
        invite.revoked_at = now
        await db.commit()
    return _invite_view(invite, now)


def _usable(now: datetime) -> tuple:
    """SQL condition "the code is valid": not revoked, not expired, not used up — the same as invite_state == "active"."""
    return (
        Invite.revoked_at.is_(None),
        or_(Invite.expires_at.is_(None), Invite.expires_at > now),
        or_(Invite.max_uses.is_(None), Invite.uses < Invite.max_uses),
    )


async def invite_usable(db: AsyncSession, code: str | None) -> bool:
    """Whether registration will accept this code right now (for a hint in the form; the deduction is consume_invite)."""
    code = normalize_code(code)
    if not code:
        return False
    return await db.scalar(select(Invite.id).where(Invite.code == code, *_usable(_now()))) is not None


async def consume_invite(db: AsyncSession, code: str | None) -> bool:
    """
    One use of a code: True — deducted. Without commit: the caller commits together with account creation, and on
    rollback the deduction is undone.
    """
    code = normalize_code(code)
    if not code:
        return False
    used = await db.execute(
        update(Invite).where(Invite.code == code, *_usable(_now())).values(uses=Invite.uses + 1).returning(Invite.id)
    )
    return used.scalar_one_or_none() is not None


# --- problem reports -----------------------------------------------------------------------------------------

def _clip(value: str | None, limit: int) -> str | None:
    return " ".join((value or "").split())[:limit] or None


async def submit_feedback(db: AsyncSession, user_id: int | None, message: str, page: str | None,
                          language: str | None, screen: str | None) -> Feedback:
    """
    A "Report a problem" message: text shorter than MESSAGE_MIN — refused, longer than MESSAGE_MAX — truncated; the page,
    app version, language and screen size are attached to the text. user_id empty — a message from a guest. The app
    version is taken by the server from its own settings (settings.VERSION), not from the client.
    """
    # Line breaks in the text are kept (reproduction steps), extra spaces at the edges are not.
    text = "\n".join(line.rstrip() for line in message.strip().splitlines())[:MESSAGE_MAX]
    if len(text) < MESSAGE_MIN:
        raise DomainError("feedback_invalid")
    item = Feedback(
        user_id=user_id, message=text, page=_clip(page, 200), app_version=settings.VERSION[:20],
        language=language if language in LANGUAGES else None, screen=_clip(screen, 20),
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


def _feedback_view(item: Feedback, username: str | None) -> dict:
    return {
        "id": item.id, "message": item.message, "page": item.page, "app_version": item.app_version,
        "language": item.language, "screen": item.screen, "status": item.status, "author": username,
        "created_at": _iso(item.created_at), "updated_at": _iso(item.updated_at),
    }


async def feedback_queue(db: AsyncSession, moderator: User, status: str | None = None) -> dict:
    """
    Reports for the moderator: without status — the unhandled ones (new and in_progress), oldest first; with status — only
    that one, newest first. At most FEEDBACK_PAGE_SIZE reports. counts is how many reports there are in total in each status.
    """
    _moderator(moderator)
    if status is not None and status not in FEEDBACK_STATUSES:
        raise DomainError("feedback_invalid")
    query = select(Feedback, User.username).outerjoin(User, Feedback.user_id == User.id)
    if status is None:
        query = query.where(Feedback.status.in_(OPEN_STATUSES)).order_by(Feedback.created_at, Feedback.id)
    else:
        query = query.where(Feedback.status == status).order_by(Feedback.created_at.desc(), Feedback.id.desc())
    rows = (await db.execute(query.limit(FEEDBACK_PAGE_SIZE))).all()
    found = dict((await db.execute(select(Feedback.status, func.count()).group_by(Feedback.status))).tuples().all())
    return {
        "items": [_feedback_view(item, username) for item, username in rows],
        "counts": {name: int(found.get(name, 0)) for name in FEEDBACK_STATUSES},
    }


async def set_feedback_status(db: AsyncSession, moderator: User, feedback_id: int, status: str) -> Feedback:
    """
    A problem report's status is changed by a moderator (values — FEEDBACK_STATUSES); the reviewer and the time are
    remembered.
    """
    _moderator(moderator)
    if status not in FEEDBACK_STATUSES:
        raise DomainError("feedback_invalid")
    item = await db.get(Feedback, feedback_id)
    if item is None:
        raise DomainError("feedback_not_found")
    item.status, item.moderator_id, item.updated_at = status, moderator.id, _now()
    await db.commit()
    return item


# --- summary for a period ----------------------------------------------------------------------------------------------

@dataclass
class DigestItem:
    """One report in the feedback summary."""
    id: int
    created_at: datetime
    status: str
    author: str | None
    message: str
    page: str | None
    app_version: str | None
    language: str | None
    screen: str | None


@dataclass
class Digest:
    """
    Feedback summary for a period: reports, counts by status and by site section, the unhandled remainder and information on
    invitations.
    """
    since: datetime
    until: datetime
    items: list[DigestItem] = field(default_factory=list)
    by_status: dict[str, int] = field(default_factory=dict)
    by_page: list[tuple[str, int]] = field(default_factory=list)
    # Total unhandled at the end of the period (including those that arrived earlier).
    backlog: int = 0
    # Invitations: how many people registered through codes over all time (sum of invites.uses) and how many codes
    # are valid at the time the summary is built.
    invited: int = 0
    active_invites: int = 0


def page_section(page: str | None) -> str:
    """Site section by page path: "/puzzles/123?x=1" → "/puzzles"."""
    path = (page or "").split("?")[0].split("#")[0].strip()
    if not path.startswith("/"):
        return "?"
    head = path.split("/")[1]
    return f"/{head}" if head else "/"


async def build_digest(db: AsyncSession, since: datetime, until: datetime) -> Digest:
    """Builds the feedback summary for the period [since, until) — for scripts/feedback_digest.py."""
    rows = (await db.execute(
        select(Feedback, User.username).outerjoin(User, Feedback.user_id == User.id)
        .where(Feedback.created_at >= since, Feedback.created_at < until).order_by(Feedback.created_at, Feedback.id)
    )).all()
    digest = Digest(since=since, until=until)
    for item, username in rows:
        created = _aware(item.created_at) or since
        digest.items.append(DigestItem(item.id, created, item.status, username, item.message, item.page,
                                       item.app_version, item.language, item.screen))
    digest.by_status = {name: sum(1 for item in digest.items if item.status == name) for name in FEEDBACK_STATUSES}
    # More frequently mentioned sections first; reports without a page ("?") at the end of their group.
    pages = Counter(page_section(item.page) for item in digest.items)
    digest.by_page = sorted(pages.items(), key=lambda pair: (-pair[1], pair[0] == "?", pair[0]))
    digest.backlog = int(await db.scalar(
        select(func.count(Feedback.id)).where(Feedback.status.in_(OPEN_STATUSES), Feedback.created_at < until)) or 0)
    now = _now()
    invites = (await db.execute(select(Invite))).scalars().all()
    digest.invited = sum(invite.uses for invite in invites)
    digest.active_invites = sum(1 for invite in invites if invite_state(invite, now) == "active")
    return digest
