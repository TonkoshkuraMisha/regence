# --- FILE: src/services/coach_cards.py ---
"""
The "club coach" after a game (task 5 of the owner's plan, 18.11): up to three one-click action cards in the game
summary (frontend GameSummaryPanel). The service only assembles what is ready — the engine is not called:

* "Fix your blunder" — a personal puzzle from this game (personal_puzzles: created by the background analysis, src/worker/
  tasks.py) with the largest move loss (personal_puzzles.cp_loss); the solution is not given away, the answer is an ordinary
  POST /puzzles/personal/{id}/answer;
* "Opening deviation" — where the game left the player's repertoire (repertoire_deviations.for_game), the selection rule is
  pick_deviation;
* "Lesson on the mistake's theme" — the themes of the costliest mistake (the themes of the same personal puzzle) in order of
  significance; which module
  of the Big Course covers them is decided by the client: the course is its data (frontend/src/content/supercourse.ts).

Called by GET /after-game/{game_id} (src/api/learn.py). Data — the tables personal_puzzles and repertoire_deviations,
games.analysis_json.

analysed — the game analysis is ready (games.analysis_json). Personal puzzles appear a few seconds after the analysis
(the same background task), so with analysed and an empty puzzle the client asks again (POLL in GameSummaryPanel).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.game import Game
from src.models.puzzle import PersonalPuzzle
from src.services import personal_puzzles, repertoire_deviations

# Deviations that give something to act on, in order of importance: one's own move off the repertoire — a memory error; the
# opponent's new move
# — a gap in preparation. "The line ended" and "went through fully" give no card.
ACTIONABLE_DEVIATIONS = ("you_left", "opponent_new")


def pick_deviation(results: list[dict]) -> dict | None:
    """
    One deviation for a card from the for_game results: first the kind by ACTIONABLE_DEVIATIONS, within a kind — the
    earliest in the game (leaving preparation earlier matters more). None — nothing to act on.
    """
    actionable = [r for r in results if r["kind"] in ACTIONABLE_DEVIATIONS]
    if not actionable:
        return None
    return min(actionable, key=lambda r: (ACTIONABLE_DEVIATIONS.index(r["kind"]), r["ply"]))


async def costliest_puzzle(db: AsyncSession, game_id: int, user_id: int) -> PersonalPuzzle | None:
    """The player's personal puzzle from this game with the largest move loss; on equal loss — the earlier one."""
    return await db.scalar(
        select(PersonalPuzzle).where(PersonalPuzzle.game_id == game_id, PersonalPuzzle.user_id == user_id)
        .order_by(PersonalPuzzle.cp_loss.desc(), PersonalPuzzle.ply).limit(1)
    )


async def for_game(db: AsyncSession, game: Game, user_id: int) -> dict:
    """
    The player's cards for their finished game (the "own and finished" check is done by the route):
    {game_id, analysed, puzzle (personal_puzzles.view) | None, deviation | None, lesson_themes: [theme codes]}.
    """
    puzzle = await costliest_puzzle(db, game.id, user_id)
    deviation = pick_deviation((await repertoire_deviations.for_game(db, game, user_id))["results"])
    return {
        "game_id": game.id,
        "analysed": game.analysis_json is not None,
        "puzzle": personal_puzzles.view(puzzle) if puzzle is not None else None,
        "deviation": deviation,
        "lesson_themes": personal_puzzles.split_themes(puzzle.themes) if puzzle is not None else [],
    }
