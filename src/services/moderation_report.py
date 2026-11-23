# --- FILE: src/services/moderation_report.py ---
"""
Summary of violations for the owner and moderators (task 26.4, "violation reports"): over the last REPORT_DAYS days -
how many reports arrived and were closed, a breakdown by kind and decision, the queue now and the age of the oldest open
report, the number of flagged offenders and the players complained about most often. Source - the reports and users tables;
read-only, changes nothing. Served by GET /moderation/summary (moderator only); the client assembles the texts.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.moderation import Report
from src.models.user import User

# Summary window in days and how many players with the most reports to show.
REPORT_DAYS = 30
TOP_TARGETS = 5


async def summary(db: AsyncSession, now: datetime | None = None) -> dict:
    """Summary {days, opened, resolved, open_now, oldest_open_hours, by_kind, by_action, cheaters, top_targets}."""
    now = now or datetime.now(UTC)
    since = now - timedelta(days=REPORT_DAYS)

    window = (await db.execute(select(Report.kind, Report.status, Report.action).where(Report.created_at >= since))).all()
    by_kind: dict[str, int] = {}
    by_action: dict[str, int] = {}
    for kind, status, action in window:
        by_kind[kind] = by_kind.get(kind, 0) + 1
        if status == "resolved" and action:
            by_action[action] = by_action.get(action, 0) + 1

    open_created = (await db.execute(select(Report.created_at).where(Report.status == "open"))).scalars().all()
    oldest = min(open_created, default=None)
    oldest_hours = None
    if oldest is not None:
        oldest = oldest if oldest.tzinfo else oldest.replace(tzinfo=UTC)
        oldest_hours = int((now - oldest).total_seconds() // 3600)

    cheaters = (await db.execute(select(func.count(User.id)).where(User.is_cheater.is_(True)))).scalar_one()
    # Automatic flag checks and appeals are not counted as people's complaints against a player.
    top = (await db.execute(
        select(User.username, func.count(Report.id).label("n"))
        .join(User, User.id == Report.target_id)
        .where(Report.created_at >= since, Report.kind.in_(("player", "message", "content")))
        .group_by(User.username).order_by(func.count(Report.id).desc(), User.username).limit(TOP_TARGETS)
    )).all()
    return {
        "days": REPORT_DAYS,
        "opened": len(window),
        "resolved": sum(1 for _, status, _ in window if status == "resolved"),
        "open_now": len(open_created),
        "oldest_open_hours": oldest_hours,
        "by_kind": by_kind,
        "by_action": by_action,
        "cheaters": int(cheaters),
        "top_targets": [{"username": name, "reports": int(n)} for name, n in top],
    }
