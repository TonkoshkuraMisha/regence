# --- FILE: tests/test_puzzles_api.py ---
"""Puzzle-solving API (task 13.2): the solution is not sent to the client, the server checks every move, rating, hints."""

import datetime as dt

import pytest
from sqlalchemy import select

from src.models.puzzle import PuzzleAttempt
from src.services import puzzles as service
from src.services.puzzle_import import import_rows

API = "/api/v1/puzzles"


def _row(puzzle_id: str, fen: str, moves: str, tags: str, rating: int = 1500, popularity: int = 96) -> dict:
    return {"PuzzleId": puzzle_id, "FEN": fen, "Moves": moves, "Rating": str(rating), "RatingDeviation": "75",
            "Popularity": str(popularity), "NbPlays": "1000", "Themes": tags}


# Black moves the rook off the back rank; Rd8+ Re8 Rxe8# - mate in 2.
BACK_RANK = _row("BR2", "4r1k1/5ppp/8/8/8/8/3R1PPP/3R2K1 b - - 0 1", "e8e2 d2d8 e2e8 d8e8", "mateIn2 backRankMate")
# Knight fork: after ...Kh8 comes Nf7+.
FORK = _row("FK1", "r2q2k1/ppp3pp/8/4N3/8/8/PPP2PPP/R2QK2R b KQ - 0 1", "g8h8 e5f7", "fork short", rating=1450)
# Mate in 1 two ways: the solution has Ra8#, but Rd8# is also mate.
TWO_MATES = _row("TM1", "6k1/5ppp/8/8/8/8/5PPP/R2R2K1 b - - 0 1", "g8h8 a1a8", "mateIn1", rating=900)


@pytest.fixture
async def puzzles(db_session):
    await import_rows(db_session, [BACK_RANK, FORK, TWO_MATES])


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _start(client, token, theme: str | None = None) -> dict:
    response = client.get(f"{API}/next", params={"theme": theme} if theme else None, headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()


def _move(client, token, puzzle_id: int, move: str):
    return client.post(f"{API}/{puzzle_id}/move", json={"move": move}, headers=_auth(token))


async def test_solution_is_not_sent_and_moves_are_checked_one_by_one(client, token_user_1, puzzles, db_session):
    puzzle = _start(client, token_user_1, "back_rank_mate")
    assert set(puzzle) == {"id", "fen", "first_move", "rating", "themes", "goal", "color", "solution_length"}
    assert puzzle["first_move"] == "e8e2" and puzzle["color"] == "white" and puzzle["solution_length"] == 2
    assert "back_rank_mate" in puzzle["themes"]

    first = _move(client, token_user_1, puzzle["id"], "d2d8").json()
    assert first == {"correct": True, "done": False, "reply": "e2e8", "solution": None, "result": None}
    last = _move(client, token_user_1, puzzle["id"], "d8e8").json()
    assert last["correct"] and last["done"]
    result = last["result"]
    assert result["solved"] and result["rating_after"] > result["rating_before"] == 1500
    assert result["streak"] == 1

    attempts = (await db_session.execute(select(PuzzleAttempt))).scalars().all()
    assert len(attempts) == 1 and attempts[0].solved
    # The puzzle is finished: further moves on it are no longer accepted.
    assert _move(client, token_user_1, puzzle["id"], "d8e8").status_code == 409


async def test_wrong_move_ends_the_puzzle_and_shows_the_solution(client, token_user_1, puzzles):
    puzzle = _start(client, token_user_1, "fork_knight")
    body = _move(client, token_user_1, puzzle["id"], "e5d7").json()
    assert body["correct"] is False and body["done"] is True
    assert body["solution"] == ["e5f7"]
    assert body["result"]["solved"] is False and body["result"]["delta"] < 0
    assert body["result"]["streak"] == 0


async def test_any_mate_counts(client, token_user_1, puzzles):
    puzzle = _start(client, token_user_1, "mate_in_1")
    body = _move(client, token_user_1, puzzle["id"], "d1d8").json()
    assert body["correct"] and body["done"] and body["result"]["solved"]


async def test_illegal_and_foreign_moves(client, token_user_1, puzzles):
    puzzle = _start(client, token_user_1, "fork_knight")
    illegal = _move(client, token_user_1, puzzle["id"], "e5e7")
    assert illegal.status_code == 400 and illegal.json()["detail"]["code"] == "illegal_move"
    other = _move(client, token_user_1, puzzle["id"] + 999, "e5f7")
    assert other.status_code == 409 and other.json()["detail"]["code"] == "puzzle_not_active"


async def test_hints_reduce_the_gain(client, token_user_1, puzzles):
    puzzle = _start(client, token_user_1, "fork_knight")
    first = client.post(f"{API}/{puzzle['id']}/hint", headers=_auth(token_user_1)).json()
    assert first == {"from": "e5", "to": None, "hints_used": 1}
    second = client.post(f"{API}/{puzzle['id']}/hint", headers=_auth(token_user_1)).json()
    assert second == {"from": "e5", "to": "f7", "hints_used": 2}
    result = _move(client, token_user_1, puzzle["id"], "e5f7").json()["result"]
    assert result["solved"] and result["delta"] == 0
    # Solved with a hint: the streak does not grow.
    assert result["streak"] == 0


def test_rating_formula():
    assert service.rating_delta(1500, 1500, 0, True, 0) == 20
    assert service.rating_delta(1500, 1500, 0, True, 1) == 10
    assert service.rating_delta(1500, 1500, 0, True, 2) == 0
    assert service.rating_delta(1500, 1500, 0, False, 2) == -20
    assert service.rating_delta(1500, 1500, 100, True, 0) == 10


async def test_give_up_shows_the_rest_of_the_solution(client, token_user_1, puzzles):
    puzzle = _start(client, token_user_1, "back_rank_mate")
    _move(client, token_user_1, puzzle["id"], "d2d8")
    body = client.post(f"{API}/{puzzle['id']}/give-up", headers=_auth(token_user_1)).json()
    assert body["solution"] == ["d8e8"] and body["result"]["solved"] is False


async def test_themes_and_repeats(client, token_user_1, puzzles):
    assert client.get(f"{API}/next", params={"theme": "nonsense"}, headers=_auth(token_user_1)).status_code == 400
    assert client.get(f"{API}/next", params={"theme": "lucena"}, headers=_auth(token_user_1)).status_code == 404
    seen = set()
    for _ in range(3):
        puzzle = _start(client, token_user_1)
        seen.add(puzzle["id"])
        client.post(f"{API}/{puzzle['id']}/give-up", headers=_auth(token_user_1))
    assert len(seen) == 3  # while unsolved ones remain, there are no repeats
    # Everything has been re-solved: a puzzle is still served.
    assert _start(client, token_user_1)["id"] in seen


async def test_daily_puzzle_is_the_same_for_everyone(client, token_user_1, token_user_2, puzzles, db_session):
    first = client.get(f"{API}/daily", headers=_auth(token_user_1)).json()
    second = client.get(f"{API}/daily", headers=_auth(token_user_2)).json()
    assert first["id"] == second["id"] and first["daily"] is True
    today = dt.datetime.now(dt.UTC).date()
    other_days = {(await service.daily_puzzle(db_session, today + dt.timedelta(days=d))).id for d in range(10)}
    assert len(other_days) > 1


async def test_profile_and_auth(client, token_user_1, puzzles):
    assert client.get(f"{API}/next").status_code == 401
    puzzle = _start(client, token_user_1, "fork_knight")
    _move(client, token_user_1, puzzle["id"], "e5f7")
    profile = client.get(f"{API}/me", headers=_auth(token_user_1)).json()
    assert profile["games"] == 1 and profile["streak"] == 1 and profile["rating"] > 1500
    assert profile["history"][0]["puzzle_id"] == puzzle["id"] and profile["history"][0]["solved"] is True


# --- Timed mode (task 13.3) -------------------------------------------------------------------------------

SOLUTIONS = {row["FEN"]: row["Moves"].split()[1::2] for row in (BACK_RANK, FORK, TWO_MATES)}


def _wrong_move(view: dict) -> str:
    """A legal move for the solver that is neither from the solution nor a mate."""
    import chess

    board = chess.Board(view["fen"])
    board.push_uci(view["first_move"])
    for move in board.legal_moves:
        if move.uci() in SOLUTIONS[view["fen"]]:
            continue
        board.push(move)
        mate = board.is_checkmate()
        board.pop()
        if not mate:
            return move.uci()
    raise AssertionError("no wrong move found")

async def test_timed_run_counts_on_the_server_and_keeps_the_record(client, token_user_1, puzzles, monkeypatch):
    assert client.post(f"{API}/timed/start", json={"minutes": 4}, headers=_auth(token_user_1)).status_code == 400
    assert client.get(f"{API}/timed/next", headers=_auth(token_user_1)).status_code == 409
    run = client.post(f"{API}/timed/start", json={"minutes": 3}, headers=_auth(token_user_1)).json()
    assert run["minutes"] == 3 and run["solved"] == 0 and 170 < run["seconds_left"] <= 180

    first = client.get(f"{API}/timed/next", headers=_auth(token_user_1)).json()
    for uci in SOLUTIONS[first["fen"]]:
        body = _move(client, token_user_1, first["id"], uci).json()
    assert body["result"]["run"]["solved"] == 1
    # The rating does not change during a run.
    assert body["result"]["delta"] == 0

    second = client.get(f"{API}/timed/next", headers=_auth(token_user_1)).json()
    body = _move(client, token_user_1, second["id"], _wrong_move(second)).json()
    assert body["correct"] is False and body["result"]["run"]["mistakes"] == 1

    result = client.post(f"{API}/timed/finish", headers=_auth(token_user_1)).json()
    assert result == {"score": 1, "mistakes": 1, "minutes": 3, "best": 1, "new_record": True}
    me = client.get(f"{API}/me", headers=_auth(token_user_1)).json()
    assert me["best"] == {"3": 1, "5": 0} and me["games"] == 0
    assert client.post(f"{API}/timed/finish", headers=_auth(token_user_1)).status_code == 409
    # The run entered the leaderboards: week and all-time; other lengths and categories are rejected.
    for scope in ("week", "all"):
        board = client.get(f"{API}/timed/leaders?minutes=3&scope={scope}", headers=_auth(token_user_1)).json()
        assert [(r["place"], r["score"], r["me"]) for r in board["rows"]] == [(1, 1, True)]
        assert board["me"]["place"] == 1
    empty = client.get(f"{API}/timed/leaders?minutes=5&scope=week", headers=_auth(token_user_1)).json()
    assert empty == {"rows": [], "me": None}
    assert client.get(f"{API}/timed/leaders?minutes=4", headers=_auth(token_user_1)).status_code == 400


def test_leader_places_share_ties_and_week_starts_on_monday():
    import datetime as dt

    from src.services.puzzle_leaders import _ranked, week_start
    assert [r["place"] for r in _ranked([(1, "a", 9), (2, "b", 7), (3, "c", 7), (4, "d", 5)])] == [1, 2, 2, 4]
    assert week_start(dt.date(2026, 11, 22)) == dt.date(2026, 11, 16)   # Sunday -> Monday of the same week
    assert week_start(dt.date(2026, 11, 16)) == dt.date(2026, 11, 16)


async def test_leaders_skip_cheaters_and_keep_the_best_week_score(db_session, test_user_1, test_user_2):
    import datetime as dt

    from src.services import puzzle_leaders as pl
    today = dt.date(2026, 11, 18)
    await pl.record_week(db_session, test_user_1.id, 3, 12, today)
    await pl.record_week(db_session, test_user_1.id, 3, 8, today)      # worse: does not replace
    await pl.record_week(db_session, test_user_2.id, 3, 30, today)
    test_user_2.is_cheater = True
    await db_session.commit()
    board = await pl.leaders(db_session, 3, "week", test_user_1.id, today)
    assert [(r["username"], r["score"]) for r in board["rows"]] == [(test_user_1.username, 12)]
    assert (await pl.leaders(db_session, 3, "week", test_user_1.id, dt.date(2026, 11, 25)))["rows"] == []  # another week


async def test_timed_run_ends_after_time_or_three_mistakes(client, token_user_1, puzzles, monkeypatch):
    import time as time_module

    client.post(f"{API}/timed/start", json={"minutes": 3}, headers=_auth(token_user_1))
    now = time_module.time()
    monkeypatch.setattr(service.time, "time", lambda: now + 3 * 60 + 10)
    over = client.get(f"{API}/timed/next", headers=_auth(token_user_1))
    assert over.status_code == 409 and over.json()["detail"]["code"] == "timed_run_over"
