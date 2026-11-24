# --- FILE: src/services/notifications.py ---
"""
Notification centre (task 17.1): recording a notification and delivering it to the player's open tabs over WebSocket (event
"notification"). Delivery is best-effort: the notification is already in the database,
and the bell will show it on the next request.

Data: the notifications table (src/models/social.py): kind, payload (parameters for the text - the client assembles the
text itself from the catalogue), read time. Routes - src/api/social.py.

Order in WebSocket handlers and background tasks: ``record`` -> release the database session -> ``deliver`` (the network
must not hold a database connection). ``push`` does both steps in a row and is suitable only for HTTP handlers.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.social import Notification

logger = logging.getLogger(__name__)

# Notification kinds: a game challenge, a rematch offer, a tournament round played, a moderator's answer to a report,
# a warm-up reminder, a comment on a post, an arena start reminder. A new kind is added here and to the
# client catalogues; an unknown kind is a programmer error (assert in ``record``).
KINDS = ("challenge", "rematch", "tournament_round", "report_answer", "workout_reminder", "post_comment",
         "arena_reminder", "arena_podium", "weekly_legends")
KEEP = 50  # how many of the latest notifications are given to the client; this module does not delete old rows from the table


def view(n: Notification) -> dict:
    """A notification in the form the client receives (both in the API response and in the WebSocket event)."""
    created = n.created_at.isoformat() if n.created_at else None
    return {"id": n.id, "kind": n.kind, "payload": n.payload or {}, "created_at": created, "read": n.read_at is not None}


async def record(db: AsyncSession, user_id: int, kind: str, payload: dict, *, commit: bool = True) -> dict:
    """
    Records a notification (without delivery); returns its form for the client. commit=False - the record stays in the
    caller's transaction (the caller commits together with its own changes).
    """
    assert kind in KINDS, kind
    notification = Notification(user_id=user_id, kind=kind, payload=payload)
    db.add(notification)
    await db.flush()
    if commit:
        await db.commit()
        await db.refresh(notification)
    return view(notification)


async def deliver(user_id: int, notification: dict) -> None:
    """Sending to open tabs - after the record and after releasing the database session (the WebSocket rule)."""
    try:
        from src.services.connection_manager import manager

        await manager.send_personal_message({"event": "notification", "notification": notification}, user_id)
    except Exception as exc:  # the notification is already recorded - a delivery failure is not critical
        logger.warning("Notification delivery failed for user %s: %s", user_id, exc)


async def push(db: AsyncSession, user_id: int, kind: str, payload: dict) -> dict:
    """Record (with commit) and deliver at once; the database session is not released meanwhile - see the module docstring."""
    notification = await record(db, user_id, kind, payload)
    await deliver(user_id, notification)
    return notification


async def latest(db: AsyncSession, user_id: int) -> dict:
    """The player's last KEEP notifications (newest first) and the number of unread (all of them, not only shown)."""
    rows = (await db.execute(
        select(Notification).where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc()).limit(KEEP)
    )).scalars().all()
    unread = await db.scalar(
        select(func.count()).select_from(Notification).where(Notification.user_id == user_id, Notification.read_at.is_(None))
    ) or 0
    return {"unread": unread, "items": [view(n) for n in rows]}


async def mark_read(db: AsyncSession, user_id: int, ids: list[int] | None) -> None:
    """Marks the player's notifications with the numbers ids as read; without ids (None or an empty list) - all unread."""
    query = update(Notification).where(Notification.user_id == user_id, Notification.read_at.is_(None))
    if ids:
        query = query.where(Notification.id.in_(ids))
    await db.execute(query.values(read_at=datetime.now(UTC)))
    await db.commit()
