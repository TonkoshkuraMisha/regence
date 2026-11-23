# --- FILE: tests/test_staunton_bot.py ---

import chess
import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.services.bots.philidor import normalize_fen_key
from src.services.bots.staunton import (
    STAUNTON_OPENING_BOOK,
    StauntonBot,
    evaluate_staunton_style_bonus,
)


def test_staunton_opening_book_initial_move():
    """Check that Staunton picks an opening move from his book."""
    bot = StauntonBot(stockfish_path=None)
    board = chess.Board()
    start_key = normalize_fen_key(board)
    expected_moves = {item[0] for item in STAUNTON_OPENING_BOOK[start_key]}

    result = bot.choose_move(board.fen())
    assert result["uci"] in expected_moves
    assert result["source"] == "opening_book"


def test_staunton_style_rewards_c4_and_castling():
    """Check that Staunton's positional filter rewards the English opening (c2-c4) and castling."""
    start_board = chess.Board()
    c4_bonus, _ = evaluate_staunton_style_bonus(start_board, chess.Move.from_uci("c2c4"))
    h3_bonus, _ = evaluate_staunton_style_bonus(start_board, chess.Move.from_uci("h2h3"))
    assert c4_bonus > h3_bonus

    castle_board = chess.Board("r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")
    castle_bonus, _ = evaluate_staunton_style_bonus(castle_board, chess.Move.from_uci("e1g1"))
    assert castle_bonus > h3_bonus


def test_staunton_middlegame_move_generation():
    """Check Staunton's move generation outside the opening book."""
    bot = StauntonBot(stockfish_path=None)
    board = chess.Board("r1bq1rk1/pp2ppbp/2np1np1/8/2PPP3/2N2N2/PP2BPPP/R1BQ1RK1 w - - 3 8")

    result = bot.choose_move(board.fen())
    assert chess.Move.from_uci(result["uci"]) in board.legal_moves
    assert result["source"] == "staunton_style_engine"


@pytest.mark.asyncio
async def test_staunton_api_move_endpoint():
    """Check the REST endpoints /api/v1/bots/list and /api/v1/bots/move for playing against Staunton."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        list_resp = await client.get("/api/v1/bots/list")
        assert list_resp.status_code == 200
        bot_ids = [b["id"] for b in list_resp.json()["bots"]]
        assert "staunton" in bot_ids

        move_resp = await client.post(
            "/api/v1/bots/move",
            json={"bot_id": "staunton", "fen": chess.STARTING_FEN},
        )
        assert move_resp.status_code == 200
        data = move_resp.json()
        assert data["bot_id"] == "staunton"
        assert data["source"] == "opening_book"
