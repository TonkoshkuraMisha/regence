# --- FILE: src/services/weekly_summary.py ---
"""
"My Week" (a retention development idea): the player's results for the last 7 days (UTC) - games, rating, puzzles, days
of activity and the warm-up streak - and one piece of advice as a code. The data is taken from the tables games (finished
non-simulation games), puzzle_attempts and trainer_results; the streak is workout.streak_status. There are no new tables.
The advice is the pure function advice_code: the server gives a code (weekly.advice.*), the client assembles the text.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.game import Game, GameStatus
from src.models.puzzle import PuzzleAttempt
from src.models.trainer import TrainerResult
from src.models.user import User
from src.services import workout

# Length of the results window in days.
WEEK_DAYS = 7
# The advice "review your losses": losses exceed wins by this factor and are no fewer than LOSS_MIN games.
LOSS_RATIO = 2
LOSS_MIN = 4


def advice_code(games: int, wins: int, losses: int, puzzles: int, days_active: int) -> str:
    """
    Advice code by the week's results (the first matching rule): comeback - there was no activity; try_puzzles - played but
    did not solve puzzles; play_games - solved puzzles but did not play; review_losses - far more losses than wins; keep_going.
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
    """The player's week results (see GET /workout/week): games, puzzles, active days, streak, advice code."""
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
