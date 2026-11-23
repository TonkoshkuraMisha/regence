# --- FILE: tests/test_puzzles_special_moves.py ---
"""
Server-side puzzle solving when the solution move is special: castling, en passant, promotion (including underpromotion and
the wrong piece), alternative mate, different move notation; the whole daily puzzle; switching puzzles mid-solution.
"""

import pytest

from src.services.puzzle_import import import_rows

API = "/api/v1/puzzles"


def _row(puzzle_id: str, fen: str, moves: str, rating: int = 1500) -> dict:
    return {"PuzzleId": puzzle_id, "FEN": fen, "Moves": moves, "Rating": str(rating), "RatingDeviation": "75",
            "Popularity": "96", "NbPlays": "1000", "Themes": "short"}


# Black plays a6 - White castles.
CASTLE = _row("CS1", "r3k2r/pppq1ppp/8/8/8/8/PPP2PPP/R3K2R b KQkq - 0 1", "a7a6 e1g1")
# Black plays d7-d5 - White captures en passant e5xd6.
EN_PASSANT = _row("EP1", "rnbqkbnr/pppppppp/8/4P3/8/8/PPPP1PPP/RNBQKBNR b KQkq - 0 2", "d7d5 e5d6")
# Black's queen goes to d6 - promotion to a knight with a fork (king g7 and queen d6).
KNIGHT_FORK = _row("UP1", "8/4P1k1/8/3q4/8/8/8/K7 b - - 0 1", "d5d6 e7e8n")
# The king goes to the corner - promotion with a back-rank mate: both queen and rook work.
PROMOTE_MATE = _row("PM1", "6k1/P4ppp/8/8/8/8/8/K7 b - - 0 1", "g8h8 a7a8q")


@pytest.fixture
async def special(db_session):
    added, _ = await import_rows(db_session, [CASTLE, EN_PASSANT, KNIGHT_FORK, PROMOTE_MATE])
    assert added == 4


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _open(client, token, puzzle_id: str) -> dict:
    """Puzzle by its source number: the pick is random, so retry until the wanted one comes up."""
    for _ in range(60):
        view = client.get(f"{API}/next", headers=_auth(token)).json()
        if view["fen"] == {"CS1": CASTLE, "EP1": EN_PASSANT, "UP1": KNIGHT_FORK, "PM1": PROMOTE_MATE}[puzzle_id]["FEN"]:
            return view
    raise AssertionError(f"puzzle {puzzle_id} not served")


def _move(client, token, puzzle_id: int, move: str):
    return client.post(f"{API}/{puzzle_id}/move", json={"move": move}, headers=_auth(token))


@pytest.mark.parametrize(("source", "move"), [
    ("CS1", "e1g1"),
    ("EP1", "e5d6"),
    ("UP1", "e7e8n"),
    ("PM1", "a7a8q"),
])
async def test_special_solution_moves_are_accepted(client, token_user_1, special, source, move):
    view = _open(client, token_user_1, source)
    body = _move(client, token_user_1, view["id"], move).json()
    assert body["correct"] and body["done"] and body["result"]["solved"], body


async def test_any_promotion_that_mates_counts(client, token_user_1, special):
    view = _open(client, token_user_1, "PM1")
    body = _move(client, token_user_1, view["id"], "a7a8r").json()  # the solution has a queen, but the rook mates too
    assert body["correct"] and body["result"]["solved"]


async def test_wrong_promotion_piece_is_a_mistake(client, token_user_1, special):
    view = _open(client, token_user_1, "UP1")
    body = _move(client, token_user_1, view["id"], "e7e8q").json()
    assert not body["correct"] and body["solution"] == ["e7e8n"]


@pytest.mark.parametrize("bad", ["e7e8", "e7e8k", "e7e8Q", "e7e9n", "zzzz"])
async def test_malformed_or_illegal_promotion_is_400_and_keeps_the_puzzle(client, token_user_1, special, bad):
    view = _open(client, token_user_1, "UP1")
    response = _move(client, token_user_1, view["id"], bad)
    assert response.status_code in (400, 422), response.text
    # An invalid notation is not a move: the puzzle goes on and the correct move is still accepted.
    assert _move(client, token_user_1, view["id"], "e7e8n").json()["correct"]


async def test_castling_hint_points_to_the_king(client, token_user_1, special):
    view = _open(client, token_user_1, "CS1")
    first = client.post(f"{API}/{view['id']}/hint", headers=_auth(token_user_1)).json()
    second = client.post(f"{API}/{view['id']}/hint", headers=_auth(token_user_1)).json()
    assert first["from"] == "e1" and first["to"] is None
    assert second == {"from": "e1", "to": "g1", "hints_used": 2}


async def test_en_passant_is_not_available_before_the_double_step(client, token_user_1, special):
    """The move d6 is impossible before the opponent's move: the solver's position is after d7-d5."""
    view = _open(client, token_user_1, "EP1")
    assert view["first_move"] == "d7d5"
    assert _move(client, token_user_1, view["id"], "e5e6").json()["correct"] is False


async def test_new_puzzle_cancels_the_unfinished_one(client, token_user_1, special):
    first = _open(client, token_user_1, "CS1")
    second = _open(client, token_user_1, "EP1")  # another puzzle is open - the first one is no longer active
    stale = _move(client, token_user_1, first["id"], "e1g1")
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "puzzle_not_active"
    assert _move(client, token_user_1, second["id"], "e5d6").json()["correct"]


async def test_daily_puzzle_can_be_solved_end_to_end(client, token_user_1, special):
    view = client.get(f"{API}/daily", headers=_auth(token_user_1)).json()
    solution = {row["FEN"]: row["Moves"].split()[1] for row in (CASTLE, EN_PASSANT, KNIGHT_FORK, PROMOTE_MATE)}
    body = _move(client, token_user_1, view["id"], solution[view["fen"]]).json()
    assert body["correct"] and body["result"]["solved"]


async def test_moves_without_login_are_refused(client, special):
    assert client.post(f"{API}/1/move", json={"move": "e2e4"}).status_code == 401
