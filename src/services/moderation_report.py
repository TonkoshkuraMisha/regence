# --- FILE: src/services/moderation_report.py ---
"""
Сводка по нарушениям для владельца и модераторов (таск 26.4, «отчёты о нарушениях»): за последние REPORT_DAYS суток —
сколько заявок поступило и закрыто, разбивка по видам и решениям, очередь сейчас и возраст самой старой открытой
заявки, число помеченных нарушителей и игроки, на которых жаловались чаще всего. Источник — таблицы reports и users;
только чтение, ничего не меняет. Выдача — GET /moderation/summary (только модератор); тексты собирает клиент.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.moderation import Report
from src.models.user import User

# Окно сводки в сутках и сколько игроков с наибольшим числом заявок показывать.
REPORT_DAYS = 30
TOP_TARGETS = 5


async def summary(db: AsyncSession, now: datetime | None = None) -> dict:
    """Сводка {days, opened, resolved, open_now, oldest_open_hours, by_kind, by_action, cheaters, top_targets}."""
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
    # Автоматические проверки флага и апелляции не считаются жалобами людей на игрока.
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
