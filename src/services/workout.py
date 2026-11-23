"""
Daily warm-up (task 22.2) - 10-15 minutes from existing training, without new tables:

1. 5 puzzles on the weakest themes (skills map 22.1; without data - basic themes);
2. 1 a vision or counting trainer (19.x) - the one the player did least often;
3. repetition of openings by schedule (20.2), if there are cards to repeat;
4. 1 "your mistake" (13.5), if there are positions from own games to repeat.

A step is credited from the trainings themselves for today (UTC), so there is nothing to fake it with. A warm-up day is done if
5 puzzles are solved and a trainer is completed; the streak is how many days in a row this was so (today may still be in
progress).
"""

from collections import Counter
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.puzzle import PersonalPuzzle, PuzzleAttempt
from src.models.repertoire import Repertoire, RepertoireCard
from src.models.trainer import TrainerResult
from src.models.user import User
from src.services import skills

# Puzzles per day: the norm of a completed warm-up and the goal of the "puzzles" step.
PUZZLES = 5
# How many of the weakest themes (skills.tactics) are taken for the "puzzles" step.
WEAK_THEMES = 3
# Default themes when there is no skills map data on the player yet.
DEFAULT_THEMES = ("fork", "pin", "back_rank_mate")
# Vision and counting trainers (trainer_results.trainer), of which one is chosen per day.
TRAINERS = ("coord_find", "coord_name", "blind_where", "calc_checks", "calc_exchange", "calc_square",
            "memory_position", "knight_route")
# Window in days in which the streak is counted: it is no longer than this value.
STREAK_DAYS = 60


def day_of(moment: datetime) -> date:
    """Calendar day (UTC); a moment without a time zone is treated as UTC."""
    return (moment if moment.tzinfo else moment.replace(tzinfo=UTC)).astimezone(UTC).date()


async def _days(db: AsyncSession, column, user_column, user_id: int, since: datetime) -> Counter[date]:
    """How many records (puzzle attempts or trainers) the player has on each day starting from since."""
    rows = (await db.execute(select(column).where(user_column == user_id, column >= since))).scalars().all()
    return Counter(day_of(moment) for moment in rows if moment is not None)


async def streak_status(db: AsyncSession, user_id: int, now: datetime) -> tuple[bool, int]:
    """Whether the warm-up is done today and the streak length (days in a row, including today if done)."""
    today = day_of(now)
    start = datetime(today.year, today.month, today.day, tzinfo=UTC)
    since = start - timedelta(days=STREAK_DAYS)
    puzzle_days = await _days(db, PuzzleAttempt.created_at, PuzzleAttempt.user_id, user_id, since)
    trainer_days = await _days(db, TrainerResult.created_at, TrainerResult.user_id, user_id, since)

    def complete(day: date) -> bool:
        return puzzle_days[day] >= PUZZLES and trainer_days[day] >= 1

    streak = 0
    day = today if complete(today) else today - timedelta(days=1)
    while complete(day):
        streak += 1
        day -= timedelta(days=1)
    return complete(today), streak


async def plan(db: AsyncSession, user: User, now: datetime) -> dict:
    """
    Warm-up plan for today: steps (puzzles on weak themes, a trainer, opening repetition, own mistake), what is already
    done and how many days in a row the warm-up has been done.
    """
    today = day_of(now)
    start = datetime(today.year, today.month, today.day, tzinfo=UTC)
    since = start - timedelta(days=STREAK_DAYS)
    puzzle_days = await _days(db, PuzzleAttempt.created_at, PuzzleAttempt.user_id, user.id, since)
    trainer_days = await _days(db, TrainerResult.created_at, TrainerResult.user_id, user.id, since)

    _, weakest = await skills.tactics(db, user.id)
    themes = [w["theme"] for w in weakest][:WEAK_THEMES] or list(DEFAULT_THEMES)

    tried = dict((await db.execute(
        select(TrainerResult.trainer, func.count()).where(TrainerResult.user_id == user.id,
                                                          TrainerResult.trainer.in_(TRAINERS))
        .group_by(TrainerResult.trainer)
    )).tuples().all())
    trainer = min(TRAINERS, key=lambda key: (tried.get(key, 0), TRAINERS.index(key)))

    due_rows = (await db.execute(
        select(Repertoire.id, func.count()).join(RepertoireCard, RepertoireCard.repertoire_id == Repertoire.id)
        .where(Repertoire.user_id == user.id, RepertoireCard.due_at.is_not(None), RepertoireCard.due_at <= now)
        .group_by(Repertoire.id)
    )).tuples().all()
    repertoire_due = sum(count for _, count in due_rows)
    repertoire_id = max(due_rows, key=lambda row: row[1])[0] if due_rows else None

    mistakes_due = await db.scalar(select(func.count()).select_from(PersonalPuzzle).where(
        PersonalPuzzle.user_id == user.id, PersonalPuzzle.done.is_(False), PersonalPuzzle.due_at <= now)) or 0

    def complete(day: date) -> bool:
        return puzzle_days[day] >= PUZZLES and trainer_days[day] >= 1

    streak = 0
    day = today if complete(today) else today - timedelta(days=1)
    while complete(day):
        streak += 1
        day -= timedelta(days=1)

    return {
        "date": today.isoformat(),
        "complete": complete(today),
        "streak": streak,
        "steps": [
            {"kind": "puzzles", "themes": themes, "target": PUZZLES, "done": min(puzzle_days[today], PUZZLES)},
            {"kind": "trainer", "trainer": trainer, "done": trainer_days[today] >= 1},
            {"kind": "repertoire", "due": repertoire_due, "repertoire_id": repertoire_id, "done": repertoire_due == 0},
            {"kind": "mistake", "due": mistakes_due, "done": mistakes_due == 0},
        ],
    }


def utcnow() -> datetime:
    """Current time in UTC; extracted so that tests and callers can replace the clock."""
    return datetime.now(UTC)


async def send_reminders(db: AsyncSession, now: datetime) -> int:
    """
    Warm-up reminder (a scheduled Celery beat task, once a day): to players with a running streak who have not yet warmed
    up today; no more than one reminder a day. Returns the number sent.
    """
    from src.models.social import Notification
    from src.services import notifications

    today = day_of(now)
    start = datetime(today.year, today.month, today.day, tzinfo=UTC)
    recent = start - timedelta(days=1)
    active = set((await db.execute(select(PuzzleAttempt.user_id).where(PuzzleAttempt.created_at >= recent))).scalars())
    active &= set((await db.execute(select(TrainerResult.user_id).where(TrainerResult.created_at >= recent))).scalars())
    reminded = set((await db.execute(select(Notification.user_id).where(
        Notification.kind == "workout_reminder", Notification.created_at >= start))).scalars())
    sent = 0
    for user_id in sorted(active - reminded):
        done, streak = await streak_status(db, user_id, now)
        if done or streak == 0:
            continue
        notification = await notifications.record(db, user_id, "workout_reminder", {"streak": streak})
        await notifications.deliver(user_id, notification)
        sent += 1
    return sent
