# --- FILE: src/services/puzzle_leaders.py ---
"""
Таблица лидеров забегов на время (таск 26.1, «соревнование по задачам»). Два зачёта для каждой длины забега (3 и 5 минут):
«неделя» — лучшие счёта текущей недели (понедельник UTC → понедельник; таблица puzzle_timed_scores, которую пополняет
record_week при завершении забега) и «всё время» — рекорды игроков (users.puzzle_best_3 / puzzle_best_5). В таблицу не
попадают нарушители честной игры (is_cheater), боты и удалённые аккаунты. Игрок видит и своё место, если оно ниже топа.
Забеги на время играются по правилам puzzles.start_run; здесь только учёт и выдача.
"""

import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.puzzle import PuzzleTimedScore
from src.models.user import User

# Длины забегов, по которым ведётся таблица (как puzzles.TIMED_MINUTES), и зачёты.
MINUTES = (3, 5)
SCOPES = ("week", "all")
# Сколько мест показывает таблица.
TOP = 20


def week_start(day: dt.date) -> dt.date:
    """Понедельник недели, в которую попадает день (UTC)."""
    return day - dt.timedelta(days=day.weekday())


def _eligible():
    """Кто попадает в таблицу: живые игроки без пометки нарушителя."""
    return (User.is_cheater == False, User.is_bot == False, User.deleted_at.is_(None))  # noqa: E712


async def record_week(db: AsyncSession, user_id: int, minutes: int, score: int, today: dt.date | None = None) -> None:
    """
    Запоминает счёт забега в недельной таблице: строка игрока за неделю хранит лучший счёт. Без commit — его делает
    вызывающий. Забеги одного игрока идут по одному (забег в Redis один), поэтому гонки на строке нет.
    """
    if minutes not in MINUTES or score <= 0:
        return
    week = week_start(today or dt.datetime.now(dt.UTC).date())
    row = await db.scalar(select(PuzzleTimedScore).where(
        PuzzleTimedScore.user_id == user_id, PuzzleTimedScore.minutes == minutes, PuzzleTimedScore.week == week))
    if row is None:
        db.add(PuzzleTimedScore(user_id=user_id, minutes=minutes, week=week, score=score))
    elif score > row.score:
        row.score = score


def _ranked(rows: list[tuple[int, str, int]]) -> list[dict]:
    """Места по убыванию счёта; равные счета делят место (1, 2, 2, 4)."""
    out: list[dict] = []
    for index, (user_id, username, score) in enumerate(rows):
        place = out[-1]["place"] if out and out[-1]["score"] == score else index + 1
        out.append({"place": place, "user_id": user_id, "username": username, "score": score})
    return out


async def leaders(
        db: AsyncSession, minutes: int, scope: str, user_id: int | None = None, today: dt.date | None = None,
) -> dict:
    """
    Таблица {rows: [{place, username, score, me}], me: моя строка или None}. rows — топ TOP; me — строка игрока,
    если он в зачёте (в том числе ниже топа). Неизвестная длина или зачёт — пустая таблица.
    """
    if minutes not in MINUTES or scope not in SCOPES:
        return {"rows": [], "me": None}
    if scope == "week":
        week = week_start(today or dt.datetime.now(dt.UTC).date())
        query = (select(User.id, User.username, PuzzleTimedScore.score)
                 .join(PuzzleTimedScore, PuzzleTimedScore.user_id == User.id)
                 .where(PuzzleTimedScore.minutes == minutes, PuzzleTimedScore.week == week, *_eligible()))
        score_column = PuzzleTimedScore.score
    else:
        score_column = getattr(User, f"puzzle_best_{minutes}")
        query = select(User.id, User.username, score_column).where(score_column > 0, *_eligible())
    everyone = (await db.execute(query.order_by(score_column.desc(), User.username))).all()
    ranked = _ranked([(row[0], row[1], row[2]) for row in everyone])
    rows = [{"place": r["place"], "username": r["username"], "score": r["score"], "me": r["user_id"] == user_id}
            for r in ranked[:TOP]]
    mine = next((r for r in ranked if r["user_id"] == user_id), None) if user_id is not None else None
    me = {"place": mine["place"], "username": mine["username"], "score": mine["score"], "me": True} if mine else None
    return {"rows": rows, "me": me}
