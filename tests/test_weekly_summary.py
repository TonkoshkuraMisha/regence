""""My week": summary of the last 7 days by games, puzzles and active days; advice as a code."""

from datetime import UTC, datetime, timedelta

import pytest

from src.models.game import Game, GameStatus
from src.models.puzzle import Puzzle, PuzzleAttempt
from src.services import weekly_summary
from src.services.weekly_summary import advice_code

NOW = datetime(2026, 11, 22, 12, tzinfo=UTC)


def test_advice_rules_in_order():
    assert advice_code(0, 0, 0, 0, 0) == "comeback"
    assert advice_code(3, 1, 1, 0, 2) == "try_puzzles"
    assert advice_code(0, 0, 0, 5, 2) == "play_games"
    assert advice_code(5, 1, 4, 3, 3) == "review_losses"
    assert advice_code(5, 3, 2, 3, 3) == "keep_going"
    assert advice_code(2, 0, 2, 3, 3) == "keep_going"   # fewer losses than LOSS_MIN - no scolding


@pytest.fixture
async def puzzle(db_session):
    item = Puzzle(source="lichess", source_id="wk1", fen="8/8/8/8/8/8/8/K6k w - - 0 1", moves="a1a2", rating=1500)
    db_session.add(item)
    await db_session.commit()
    return item


async def test_week_counts_only_my_recent_finished_games_and_attempts(db_session, test_user_1, test_user_2, puzzle):
    me, other = test_user_1.id, test_user_2.id

    def game(white, black, result, days_ago, **extra):
        db_session.add(Game(white_player_id=white, black_player_id=black, status=GameStatus.COMPLETED, result=result,
                            finished_at=NOW - timedelta(days=days_ago, hours=1), **extra))

    game(me, other, "1-0", 1, white_rating_delta=8, black_rating_delta=-8)      # win as White
    game(other, me, "1-0", 2, white_rating_delta=6, black_rating_delta=-6)      # loss as Black
    game(me, other, "1/2-1/2", 3, white_rating_delta=0, black_rating_delta=0)   # draw
    game(me, other, "1-0", 9, white_rating_delta=50, black_rating_delta=-50)    # older than a week - not counted
    game(other, other, "1-0", 1)                                               # someone else's game
    for solved in (True, True, False):
        db_session.add(PuzzleAttempt(user_id=me, puzzle_id=puzzle.id, solved=solved, rating_before=1500, rating_after=1500,
                                     created_at=NOW - timedelta(days=1, hours=2)))
    await db_session.commit()

    week = await weekly_summary.build(db_session, test_user_1, NOW)
    assert week["games"] == {"total": 3, "wins": 1, "draws": 1, "losses": 1, "rating_delta": 8 - 6}
    assert week["puzzles"] == {"attempts": 3, "solved": 2}
    assert week["days_active"] == 3          # days -1, -2 and -3 (yesterday has both a game and puzzles)
    assert week["advice"] == "keep_going"


async def test_week_endpoint_needs_login_and_returns_comeback_for_idle_player(client, token_user_1):
    assert client.get("/api/v1/workout/week").status_code == 401
    body = client.get("/api/v1/workout/week", headers={"Authorization": f"Bearer {token_user_1}"}).json()
    assert body["games"]["total"] == 0 and body["advice"] == "comeback" and body["days_active"] == 0
