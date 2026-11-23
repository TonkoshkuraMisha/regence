# --- FILE: tests/test_custom_start_position.py ---
"""
A bot game and analysis from an arbitrary starting position: moves are validated from it, the PGN gets
SetUp/FEN headers, game review numbers moves by the board, impossible positions are rejected.
"""

import io

import chess
import chess.pgn
import pytest

from src.models.game import Game, GameStatus
from src.services.analysis_service import _evaluate_board_sequence_sync
from src.services.game_engine import (
    STARTING_FEN,
    InvalidStartPositionError,
    board_from_start_fen,
    is_standard_start,
    restore_board,
    validate_start_fen,
)

API = "/api/v1"
# King and queen against king, white to move: Qa7# is mate in one.
KQ_VS_K = "k7/7Q/1K6/8/8/8/8/8 w - - 0 1"
# The same idea with black to move and move number 40: the game starts "from the middle".
BLACK_TO_MOVE = "6k1/5ppp/8/8/8/8/5PPP/3R2K1 b - - 0 40"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _save(client, token, **body):
    payload = {"bot_id": "philidor", "player_color": "white", "result": "1-0", **body}
    return client.post(f"{API}/bots/save-game", json=payload, headers=_auth(token))


# --- board from FEN -----------------------------------------------------------------------


@pytest.mark.parametrize("fen", [None, "", "   ", STARTING_FEN])
def test_missing_or_standard_fen_gives_the_usual_setup(fen):
    board = board_from_start_fen(fen)
    assert board.fen() == STARTING_FEN and is_standard_start(board)


@pytest.mark.parametrize("fen", [
    "not a fen",
    "8/8/8/8/8/8/8/8 w - - 0 1",        # no kings
    "kK6/8/8/8/8/8/8/8 w - - 0 1",      # kings adjacent
    "4k3/8/8/8/8/8/8/r3K3 b - - 0 1",   # white king in check, but black to move
])
def test_impossible_positions_are_rejected(fen):
    with pytest.raises(InvalidStartPositionError):
        board_from_start_fen(fen)


def test_legal_position_with_black_to_move_is_accepted():
    board = board_from_start_fen(BLACK_TO_MOVE)
    assert board.turn == chess.BLACK and board.fullmove_number == 40 and not is_standard_start(board)


# --- saving a bot game ----------------------------------------------------------------------


async def test_bot_game_from_a_position_is_saved_with_setup_headers(client, db_session, token_user_1):
    response = _save(client, token_user_1, moves_uci=["h7a7"], start_fen=KQ_VS_K)

    assert response.status_code == 200
    assert response.json()["result"] == "1-0"  # mate found by the server from the given position

    game = await db_session.get(Game, response.json()["game_id"])
    parsed = chess.pgn.read_game(io.StringIO(game.pgn))
    assert parsed.headers["SetUp"] == "1" and parsed.headers["FEN"] == KQ_VS_K
    assert "ECO" not in parsed.headers and game.eco is None  # a "from the middle" position has no opening
    assert parsed.board().fen() == KQ_VS_K
    assert parsed.end().board().is_checkmate()
    assert game.board_fen == parsed.end().board().fen()


async def test_moves_are_validated_from_the_given_position(client, token_user_1):
    # e2e4 is legal in the standard setup, but not in the "king and queen against king" position.
    response = _save(client, token_user_1, moves_uci=["e2e4"], start_fen=KQ_VS_K, termination="resignation")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "illegal_history_move"


async def test_impossible_start_position_is_a_400(client, token_user_1):
    response = _save(client, token_user_1, moves_uci=["a1a2"], start_fen="kK6/8/8/8/8/8/8/8 w - - 0 1")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_position"


async def test_standard_fen_is_not_treated_as_a_custom_position(client, db_session, token_user_1):
    response = _save(
        client, token_user_1, moves_uci=["e2e4", "e7e5"], start_fen=STARTING_FEN, termination="resignation",
        result="0-1",
    )
    assert response.status_code == 200
    game = await db_session.get(Game, response.json()["game_id"])
    assert "[FEN" not in game.pgn and game.eco is not None


async def test_game_without_start_fen_is_unchanged(client, db_session, token_user_1):
    response = _save(client, token_user_1, moves_uci=["f2f3", "e7e5", "g2g4", "d8h4"], result="0-1")
    game = await db_session.get(Game, response.json()["game_id"])
    assert response.json()["result"] == "0-1" and "[SetUp" not in game.pgn


# --- analysis -------------------------------------------------------------------------------


def test_position_analysis_accepts_a_start_position(client):
    response = client.post(f"{API}/analysis/position", json={"moves": ["Qa7#"], "start_fen": KQ_VS_K})

    assert response.status_code == 200
    board = chess.Board(response.json()["fen"])
    assert board.is_checkmate() and board.turn == chess.BLACK


def test_position_analysis_rejects_an_impossible_position(client):
    response = client.post(f"{API}/analysis/position", json={"moves": [], "start_fen": "8/8/8/8/8/8/8/8 w - - 0 1"})
    assert response.status_code == 400


def test_position_analysis_without_start_fen_still_starts_from_the_usual_setup(client):
    response = client.post(f"{API}/analysis/position", json={"moves": ["e4"]})
    assert response.json()["fen"].startswith("rnbqkbnr/pppppppp/8/8/4P3/")


def test_full_game_analysis_numbers_moves_from_the_board(monkeypatch):
    """A game starting with black to move at move 40: the first ply is "40... black", not "1. white"."""
    monkeypatch.setattr("src.services.analysis_service.resolve_stockfish_path", lambda: None)
    board = chess.Board(BLACK_TO_MOVE)
    game = chess.pgn.Game()
    game.setup(board)
    node = game
    for uci in ("g8f8", "d1d8", "f8e7"):
        node = node.add_variation(chess.Move.from_uci(uci))

    report = _evaluate_board_sequence_sync(str(game))

    assert [(m["move_number"], m["color"], m["san"]) for m in report["moves"]] == [
        (40, "black", "Kf8"), (41, "white", "Rd8+"), (41, "black", "Ke7"),
    ]
    assert [m["ply"] for m in report["moves"]] == [1, 2, 3]


# --- validate_start_fen and restore_board -----------------------------------------------------


def test_validate_start_fen_returns_canonical_fen():
    assert validate_start_fen(None) == STARTING_FEN
    assert validate_start_fen("  ") == STARTING_FEN
    assert validate_start_fen(f"  {BLACK_TO_MOVE}  ") == BLACK_TO_MOVE
    with pytest.raises(ValueError):
        validate_start_fen("kK6/8/8/8/8/8/8/8 w - - 0 1")


def _board_after(start_fen: str, *sans: str) -> chess.Board:
    board = chess.Board(start_fen)
    for san in sans:
        board.push_san(san)
    return board


def test_restore_board_replays_movetext_from_the_start_position():
    final = _board_after(BLACK_TO_MOVE, "Kf8", "Rd8+")

    board = restore_board(final.fen(), "40... Kf8 41. Rd8+", start_fen=BLACK_TO_MOVE)

    assert board.fen() == final.fen()
    assert len(board.move_stack) == 2  # history exists - needed by the repetition rules


def test_restore_board_reads_a_pgn_document_with_setup_headers():
    final = _board_after(BLACK_TO_MOVE, "Kf8", "Rd8+")
    document = "\n".join(['[SetUp "1"]', f'[FEN "{BLACK_TO_MOVE}"]', "", "40... Kf8 41. Rd8+ *"])

    board = restore_board(final.fen(), document)

    assert board.fen() == final.fen() and len(board.move_stack) == 2
    assert board.root().fen() == BLACK_TO_MOVE


def test_restore_board_falls_back_to_the_fen_when_history_does_not_fit():
    final = _board_after(BLACK_TO_MOVE, "Kf8")
    # Without start_fen the moves are replayed from the standard setup - Kf8 is impossible there.
    board = restore_board(final.fen(), "40... Kf8")
    assert board.fen() == final.fen() and board.move_stack == []


# --- result of a bot game from an arbitrary position -----------------------------------------

# Queen against a bare king: after the quiet move Qh6 the game continues.
QUIET_MOVE = ["h7h6"]


async def test_resignation_from_a_position(client, db_session, token_user_1):
    response = _save(client, token_user_1, moves_uci=QUIET_MOVE, start_fen=KQ_VS_K,
                     termination="resignation", result="0-1")

    assert response.status_code == 200 and response.json()["result"] == "0-1"
    game = await db_session.get(Game, response.json()["game_id"])
    assert game.termination == "resignation" and game.is_rated is False
    assert game.eco is None and f'[FEN "{KQ_VS_K}"]' in game.pgn


async def test_flag_against_a_bare_king_is_a_draw(client, db_session, token_user_1):
    """White's flag fell, but black has only a king - mate is impossible, so a draw (FIDE 6.9)."""
    response = _save(client, token_user_1, moves_uci=QUIET_MOVE, start_fen=KQ_VS_K,
                     termination="timeout", result="0-1")

    assert response.status_code == 200 and response.json()["result"] == "1/2-1/2"
    game = await db_session.get(Game, response.json()["game_id"])
    assert game.termination == "timeout_vs_insufficient_material" and game.is_rated is False


def test_position_analysis_from_a_black_to_move_position(client):
    response = client.post(
        f"{API}/analysis/position", json={"moves": ["Kf8", "Rd8+", "Ke7"], "start_fen": BLACK_TO_MOVE},
    )

    assert response.status_code == 200
    assert response.json()["fen"] == _board_after(BLACK_TO_MOVE, "Kf8", "Rd8+", "Ke7").fen()


def test_too_long_start_fen_is_rejected_by_the_schema(client):
    response = client.post(f"{API}/analysis/position", json={"moves": [], "start_fen": "8/" * 61})
    assert response.status_code == 422


# --- full game review from an arbitrary position ----------------------------------------------


async def test_full_game_analysis_endpoint_numbers_moves_from_the_position(client, db_session, monkeypatch):
    """A game starting with black to move at move 25: the first ply is black's 25th move, accuracy is computed."""
    from src.models.user import User

    monkeypatch.setattr("src.services.analysis_service.resolve_stockfish_path", lambda: None)
    start = "6k1/5ppp/8/8/8/8/5PPP/3R2K1 b - - 0 25"
    white, black = User(username="pos_white", hashed_password="x"), User(username="pos_black", hashed_password="x")
    db_session.add_all([white, black])
    await db_session.commit()
    game = Game(
        white_player_id=white.id, black_player_id=black.id, status=GameStatus.COMPLETED, result="1/2-1/2",
        is_rated=False,
        pgn="\n".join(['[Result "1/2-1/2"]', '[SetUp "1"]', f'[FEN "{start}"]', "", "25... Kf8 26. Rd8+ Ke7 1/2-1/2"]),
    )
    db_session.add(game)
    await db_session.commit()

    response = client.post(f"{API}/analysis/game/{game.id}")

    assert response.status_code == 200
    report = response.json()
    assert [(m["move_number"], m["color"], m["san"]) for m in report["moves"]] == [
        (25, "black", "Kf8"), (26, "white", "Rd8+"), (26, "black", "Ke7"),
    ]
    for side in ("white", "black"):
        assert 0 <= report[side]["accuracy"] <= 100
    white_moves = report["white"]
    assert sum(white_moves[key] for key in ("best", "good", "inaccuracies", "mistakes", "blunders")) == 1

