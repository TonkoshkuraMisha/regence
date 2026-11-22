# --- FILE: src/services/weekly_summary.py ---
"""
«Моя неделя» (идея развития удержания): итоги игрока за последние 7 суток (UTC) — партии, рейтинг, задачи, дни
активности и серия разминки — и один совет кодом. Данные берутся из таблиц games (завершённые партии не-симуляций),
puzzle_attempts и trainer_results; серия — workout.streak_status. Новых таблиц нет. Совет — чистая функция advice_code:
сервер отдаёт код (weekly.advice.*), текст собирает клиент.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.game import Game, GameStatus
from src.models.puzzle import PuzzleAttempt
from src.models.trainer import TrainerResult
from src.models.user import User
from src.services import workout

# Длина окна итогов в днях.
WEEK_DAYS = 7
# Совет «разберите поражения»: поражений больше побед во столько раз и не меньше LOSS_MIN партий.
LOSS_RATIO = 2
LOSS_MIN = 4


def advice_code(games: int, wins: int, losses: int, puzzles: int, days_active: int) -> str:
    """
    Код совета по итогам недели (первое подходящее правило): comeback — активности не было; try_puzzles — играл, но не
    решал задач; play_games — решал задачи, но не играл; review_losses — поражений намного больше побед; keep_going.
    """
    if days_active == 0:
        return "comeback"
    if games > 0 and puzzles == 0:
        return "try_puzzles"
    if puzzles > 0 and games == 0:
        return "play_games"
    if losses >= LOSS_MIN and losses > wins * LOSS_RATIO:
        return "review_losses"
    return "keep_going"


async def build(db: AsyncSession, user: User, now: datetime | None = None) -> dict:
    """Итоги недели игрока (поля — в ответе GET /workout/week): партии, задачи, дни активности, серия и совет кодом."""
    now = now or datetime.now(UTC)
    since = now - timedelta(days=WEEK_DAYS)

    rows = (await db.execute(
        select(Game.white_player_id, Game.result, Game.white_rating_delta, Game.black_rating_delta, Game.finished_at)
        .where(or_(Game.white_player_id == user.id, Game.black_player_id == user.id),
               Game.status == GameStatus.COMPLETED, Game.is_simulation.is_(False), Game.finished_at >= since)
    )).all()
    wins = draws = losses = 0
    rating_delta = 0
    days: set = set()
    for white_id, result, white_delta, black_delta, finished_at in rows:
        mine_white = white_id == user.id
        if result == "1/2-1/2":
            draws += 1
        elif result in ("1-0", "0-1"):
            if (result == "1-0") == mine_white:
                wins += 1
            else:
                losses += 1
        rating_delta += (white_delta if mine_white else black_delta) or 0
        days.add(workout.day_of(finished_at))

    attempts = (await db.execute(
        select(PuzzleAttempt.solved, PuzzleAttempt.created_at).where(
            PuzzleAttempt.user_id == user.id, PuzzleAttempt.created_at >= since))).all()
    solved = sum(1 for ok, _ in attempts if ok)
    days.update(workout.day_of(moment) for _, moment in attempts)
    trainer_moments = (await db.execute(
        select(TrainerResult.created_at).where(TrainerResult.user_id == user.id, TrainerResult.created_at >= since)
    )).scalars().all()
    days.update(workout.day_of(moment) for moment in trainer_moments)

    _, streak = await workout.streak_status(db, user.id, now)
    total_games = len(rows)
    return {
        "since": since.isoformat(),
        "games": {"total": total_games, "wins": wins, "draws": draws, "losses": losses, "rating_delta": rating_delta},
        "puzzles": {"attempts": len(attempts), "solved": solved},
        "days_active": len(days),
        "streak": streak,
        "advice": advice_code(total_games, wins, losses, len(attempts), len(days)),
    }
