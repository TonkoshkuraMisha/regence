# --- FILE: src/services/moderation.py ---
"""
Moderation (task 17.4).

* Report: against a player (reason: unfair play, abuse, spam, other) or against a chat message (a copy of the text).
  One open report from one player against another; against oneself - not allowed.
* The unfair-play flag is still set by the automation (src/services/anticheat.py), but now with a request in the queue for
  review (cheat_review); a flagged player can file an appeal (one open at a time).
* Moderator decisions: dismiss - reject; warn - a warning; chat_ban - disable chat for CHAT_BAN_HOURS;
  mark_cheater - confirm the flag; clear_cheater - remove the flag (and restore trust). The author of the report or appeal
  receives a "report answer" notification (notification centre, 17.1).
* Task 30.3: a report about a specific text - a direct message, a post, a comment (kind="content", subject
  "dm:id" / "post:id" / "comment:id", a copy of the text) in one step;
  something held back by the filter is a request kind="held".
  Decisions on a text: hide - remove it (hide a post, delete a message and a comment), release - release
  the held text; warn and chat_ban on a text also remove it. All open requests about the same text are closed together.
* accept - accept a suggestion for an interface text (request kind="translation", task 17.7): the decision is only
  recorded in the request, the text in the catalogue is edited by a human.

Data: all requests are the reports table (src/models/moderation.py), kinds: player, message, cheat_review, appeal,
translation, content, held. The decision is written into the request itself (status, action, moderator_id, resolved_at).
There is no separate "warning" record: warn, chat_ban and hide in a closed request within the last 30 days make a player
a "violator" with reduced communication quotas (src/services/civility.py). The chat ban is users.chat_banned_until, the unfair
play flag is users.is_cheater, trust is users.trust_factor. Which decisions are offered for which kind of request
is determined by the client (frontend/src/components/social/ModerationPage.tsx); the server checks only that the decision is in
ACTIONS and that a moderator decides (users.is_moderator). Routes - src/api/moderation.py.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DomainError
from src.models.moderation import Report
from src.models.social import DirectMessage, Post, PostComment
from src.models.user import User
from src.services import notifications

REASONS = ("cheating", "abuse", "spam", "other")  # reasons for a report that a player can choose
ACTIONS = ("dismiss", "warn", "chat_ban", "mark_cheater", "clear_cheater", "accept", "hide", "release")
TEXT_KINDS = ("content", "held")  # kinds of requests about a specific text: a report or a held text
SUBJECT_KINDS = ("dm", "post", "comment")  # what can stand in subject before the colon: the kind of text
LANGUAGES = ("en", "uk")  # languages for which translation suggestions are accepted
CHAT_BAN_HOURS = 24  # for how many hours a chat_ban decision disables communication
# Periodic review of flags (task 26.4): a flag without a human decision for longer than this many days goes back into the
# moderator's queue - the automation may have been wrong, and there must be no "eternal" flag without review.
FLAG_REVIEW_AFTER_DAYS = 60
PERIODIC_CONTEXT = "periodic"
RESTORED_TRUST = 100  # trust after the flag is removed: not lower than the starting value of users.trust_factor


def _now() -> datetime:
    return datetime.now(UTC)


def chat_banned(user: User, now: datetime | None = None) -> bool:
    """
    Whether the communication ban is in effect now (users.chat_banned_until; a time without a zone is treated as UTC).
    Checked by the game chat, direct messages and the feed.
    """
    until = user.chat_banned_until
    if until is None:
        return False
    until = until.replace(tzinfo=UTC) if until.tzinfo is None else until
    return until > (now or _now())


async def report(db: AsyncSession, reporter: User, target: User, kind: str, reason: str, comment: str | None,
                 message_text: str | None = None, game_id: int | None = None) -> Report:
    """
    A report against a player or a chat message. One cannot report oneself; from one player against another there is one open
    report (an open request of any kind counts, including a report on their text). The comment and the copy of the message
    are truncated to 300 characters.
    """
    if kind not in ("player", "message") or reason not in REASONS:
        raise DomainError("report_invalid")
    if target.id == reporter.id:
        raise DomainError("report_self")
    exists = await db.scalar(select(Report.id).where(
        Report.reporter_id == reporter.id, Report.target_id == target.id, Report.status == "open"))
    if exists is not None:
        raise DomainError("report_duplicate")
    item = Report(kind=kind, reporter_id=reporter.id, target_id=target.id, reason=reason,
                  comment=" ".join((comment or "").split())[:300] or None,
                  message_text=(message_text or "")[:300] or None, game_id=game_id)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def periodic_flag_review(db: AsyncSession, now: datetime | None = None) -> int:
    """
    Once a week (celery beat): for every player with the is_cheater flag who has no open review and whose last
    moderator decision on the flag (or last review) is older than FLAG_REVIEW_AFTER_DAYS, creates a cheat_review request
    marked periodic. Returns the number of requests created. The flag itself is not changed - a human decides.
    """
    now = now or _now()
    border = now - timedelta(days=FLAG_REVIEW_AFTER_DAYS)
    flagged = (await db.execute(select(User.id).where(User.is_cheater == True))).scalars().all()  # noqa: E712
    created = 0
    for user_id in flagged:
        open_review = await db.scalar(select(Report.id).where(
            Report.target_id == user_id, Report.kind.in_(("cheat_review", "appeal")), Report.status == "open"))
        if open_review is not None:
            continue
        last = await db.scalar(select(func.max(func.coalesce(Report.resolved_at, Report.created_at))).where(
            Report.target_id == user_id, Report.kind.in_(("cheat_review", "appeal"))))
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        if last is not None and last > border:
            continue
        db.add(Report(kind="cheat_review", reporter_id=None, target_id=user_id, reason="auto", context=PERIODIC_CONTEXT))
        created += 1
    if created:
        await db.commit()
    return created


async def flag_for_review(db: AsyncSession, user: User, game_id: int | None) -> None:
    """
    The automation (src/services/anticheat.py) flagged a player - a review request without an author, with reason auto (if
    there is no open one yet). Without commit: the calling code saves the record together with the trust penalty and the flag.
    """
    exists = await db.scalar(select(Report.id).where(
        Report.target_id == user.id, Report.kind == "cheat_review", Report.status == "open"))
    if exists is None:
        db.add(Report(kind="cheat_review", reporter_id=None, target_id=user.id, reason="auto", game_id=game_id))


async def suggest_translation(db: AsyncSession, user: User, language: str, key: str, current: str | None,
                             suggestion: str, context: str | None) -> Report:
    """
    A suggestion to fix an interface text (task 17.7): only in the "translation helper" mode
    (users.translation_helper). Request kind="translation": subject is "language:catalogue key", message_text is the current
    text, comment is the suggestion; the author and the "target" of the request are the player themselves. One open request
    per player per key.
    """
    suggestion = " ".join(suggestion.split())[:300]
    if not user.translation_helper:
        raise DomainError("translation_helper_off")
    if language not in LANGUAGES or not key or not suggestion:
        raise DomainError("report_invalid")
    subject = f"{language}:{key}"[:200]
    exists = await db.scalar(select(Report.id).where(
        Report.reporter_id == user.id, Report.kind == "translation", Report.subject == subject, Report.status == "open"))
    if exists is not None:
        raise DomainError("report_duplicate")
    item = Report(kind="translation", reporter_id=user.id, target_id=user.id, reason="other", subject=subject,
                  context=(context or "")[:200] or None, message_text=(current or "")[:300] or None, comment=suggestion)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def appeal(db: AsyncSession, user: User, comment: str | None) -> Report:
    """Appeal of a player flagged for unfair play; one can be open at a time."""
    if not user.is_cheater:
        raise DomainError("appeal_not_flagged")
    exists = await db.scalar(select(Report.id).where(
        Report.target_id == user.id, Report.kind == "appeal", Report.status == "open"))
    if exists is not None:
        raise DomainError("report_duplicate")
    item = Report(kind="appeal", reporter_id=user.id, target_id=user.id, reason="other",
                  comment=" ".join((comment or "").split())[:300] or None)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def queue(db: AsyncSession) -> list[dict]:
    """
    Open requests, oldest first; each with the names and the total number of reports against that player: reports against
    the player, against a message and against a text over all time, open and closed (automation requests about unfair play,
    appeals and translation suggestions are not counted).
    """
    open_reports = select(Report).where(Report.status == "open").order_by(Report.created_at, Report.id)
    rows = (await db.execute(open_reports)).scalars().all()
    names = {u.id: u for u in (await db.execute(
        select(User).where(User.id.in_({r.target_id for r in rows} | {r.reporter_id for r in rows if r.reporter_id}))
    )).scalars()}
    counts: dict[int, int] = {target: count for target, count in (await db.execute(
        select(Report.target_id, func.count()).where(Report.kind.in_(("player", "message", *TEXT_KINDS)))
        .group_by(Report.target_id)
    )).all()}
    result = []
    for r in rows:
        target = names.get(r.target_id)
        result.append({
            "id": r.id, "kind": r.kind, "reason": r.reason, "comment": r.comment, "message_text": r.message_text,
            "subject": r.subject, "context": r.context,
            "game_id": r.game_id, "created_at": r.created_at.isoformat() if r.created_at else None,
            "reporter": names[r.reporter_id].username if r.reporter_id in names else None,
            "target": target.username if target else None,
            "target_is_cheater": bool(target and target.is_cheater),
            "target_trust": target.trust_factor if target else None,
            "reports_on_target": counts.get(r.target_id, 0),
        })
    return result


async def resolve(db: AsyncSession, moderator: User, report_id: int, action: str) -> Report:
    """
    A moderator's decision on a request (values - ACTIONS): reject, warn, disable chat, confirm or remove the
    unfair-play flag, release or hide a held text. The author of the request receives a notification.

    Along with the request, the same decision closes: for a text - all open requests about the same text; for
    mark_cheater and clear_cheater - the open reviews and appeals of that player. The report_answer notification is received
    only by the author of the request on which the decision was made (automation requests have no author). A decision on a text
    that is not in ``_apply_to_text`` (for example, dismiss) does not change the text itself.
    """
    if not moderator.is_moderator:
        raise DomainError("moderator_only")
    if action not in ACTIONS:
        raise DomainError("report_invalid")
    item = await db.get(Report, report_id)
    if item is None or item.status != "open":
        raise DomainError("report_not_found")
    target = await db.get(User, item.target_id)
    if target is not None:
        if action == "chat_ban":
            target.chat_banned_until = _now() + timedelta(hours=CHAT_BAN_HOURS)
        elif action == "mark_cheater":
            target.is_cheater = True
        elif action == "clear_cheater":
            target.is_cheater = False
            target.trust_factor = max(target.trust_factor, RESTORED_TRUST)
    if item.kind in TEXT_KINDS and item.subject:
        await _apply_to_text(db, item.subject, action)
        for other in (await db.execute(select(Report).where(
                Report.subject == item.subject, Report.kind.in_(TEXT_KINDS), Report.status == "open",
                Report.id != item.id))).scalars():
            other.status, other.action, other.moderator_id, other.resolved_at = "resolved", action, moderator.id, _now()
    item.status, item.action, item.moderator_id, item.resolved_at = "resolved", action, moderator.id, _now()
    # The other open requests on the same flag are closed by this same decision.
    if action in ("mark_cheater", "clear_cheater"):
        for other in (await db.execute(select(Report).where(
                Report.target_id == item.target_id, Report.kind.in_(("cheat_review", "appeal")),
                Report.status == "open", Report.id != item.id))).scalars():
            other.status, other.action, other.moderator_id, other.resolved_at = "resolved", action, moderator.id, _now()
    await db.commit()
    if item.reporter_id is not None:
        await notifications.push(db, item.reporter_id, "report_answer", {"report_id": item.id, "action": action})
    return item

def _parse_subject(subject: str) -> tuple[str, int]:
    """Reference to a text "kind:id" (kind - from SUBJECT_KINDS) -> (kind, id); any other format - refusal report_invalid."""
    kind, _, raw = (subject or "").partition(":")
    if kind not in SUBJECT_KINDS or not raw.isdigit():
        raise DomainError("report_invalid")
    return kind, int(raw)


async def load_text(db: AsyncSession, subject: str) -> DirectMessage | Post | PostComment:
    """
    The text that was reported: a direct message, a post or a comment - by the subject reference of the form "kind:id".
    """
    kind, key = _parse_subject(subject)
    item: DirectMessage | Post | PostComment | None
    if kind == "dm":
        item = await db.get(DirectMessage, key)
    elif kind == "post":
        item = await db.get(Post, key)
    else:
        item = await db.get(PostComment, key)
    if item is None:
        raise DomainError("report_not_found")
    return item


def _author(item: DirectMessage | Post | PostComment) -> int:
    return item.sender_id if isinstance(item, DirectMessage) else item.author_id


async def _can_see(db: AsyncSession, item: DirectMessage | Post | PostComment, user: User) -> bool:
    """
    Whether the player can see the text they report: a direct message - only its recipient; a post and a comment -
    if not hidden and not held (for a comment - and its post too). One can report only what one sees.
    """
    if isinstance(item, DirectMessage):
        return item.recipient_id == user.id and not item.held
    if isinstance(item, Post):
        return item.hidden_at is None and not item.held
    post = await db.get(Post, item.post_id)
    return not item.held and post is not None and post.hidden_at is None and not post.held


async def report_text(db: AsyncSession, reporter: User, subject: str, reason: str) -> Report:
    """
    A report on a message, a post or a comment in one step: the text (first 300 characters) is copied into the request -
    it stays understandable even if the author deletes the text. One cannot report one's own text; from a player on one
    text there is one open report.
    """
    if reason not in REASONS:
        raise DomainError("report_invalid")
    item = await load_text(db, subject)
    author_id = _author(item)
    if author_id == reporter.id:
        raise DomainError("report_self")
    if not await _can_see(db, item, reporter):
        raise DomainError("report_not_found")
    kind, key = _parse_subject(subject)
    normalized = f"{kind}:{key}"
    exists = await db.scalar(select(Report.id).where(
        Report.reporter_id == reporter.id, Report.subject == normalized, Report.status == "open"))
    if exists is not None:
        raise DomainError("report_duplicate")
    report = Report(kind="content", reporter_id=reporter.id, target_id=author_id, reason=reason, subject=normalized,
                    message_text=(item.body or "")[:300] or None)
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report


async def _apply_to_text(db: AsyncSession, subject: str, action: str) -> None:
    """
    Applies the decision to the text itself: release lifts the hold; hide, warn and chat_ban remove the text -
    a post is hidden (hidden_at), a direct message and a comment are deleted. Other decisions do not touch the text.
    """
    try:
        item = await load_text(db, subject)
    except DomainError:
        return  # the text was already deleted by its author - the decision concerns only the player
    if action == "release":
        item.held = False
    elif action in ("hide", "warn", "chat_ban"):
        if isinstance(item, Post):
            item.hidden_at = _now()
            item.held = False
        else:
            await db.delete(item)
