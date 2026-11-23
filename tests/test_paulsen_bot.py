# --- FILE: tests/test_paulsen_bot.py ---

import chess
import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.services.bots.paulsen import (
    PAULSEN_OPENING_BOOK,
    PaulsenBot,
    evaluate_paulsen_style_bonus,
)
from src.services.bots.philidor import normalize_fen_key


def test_paulsen_opening_repertoire():
    """Check that Paulsen picks a move from his opening book."""
    bot = PaulsenBot(stockfish_path=None)
    board = chess.Board()
    start_key = normalize_fen_key(board)
    expected_moves = {item[0] for item in PAULSEN_OPENING_BOOK[start_key]}

    result = bot.choose_move(board.fen())
    assert result["uci"] in expected_moves
    assert result["source"] == "opening_book"


def test_paulsen_style_rewards_flexible_pawn_shield_and_bishops():
    """Check that the Paulsen style filter rewards Sicilian set-ups (c5/e6/a6) and bishop fianchetto."""
    board = chess.Board("rnbqkbnr/pp1ppppp/8/2p5/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2")

    e6_bonus, _ = evaluate_paulsen_style_bonus(board, chess.Move.from_uci("e7e6"))
    h6_bonus, _ = evaluate_paulsen_style_bonus(board, chess.Move.from_uci("h7h6"))
    assert e6_bonus > h6_bonus


def test_paulsen_middlegame_move_generation():
    """Check Paulsen move generation in the middlegame, outside the book."""
    bot = PaulsenBot(stockfish_path=None)
    board = chess.Board("r1bq1rk1/1p2bppp/p1nppn2/8/3NP3/2N1B3/PPPQBPPP/2KR3R b - - 3 10")

    result = bot.choose_move(board.fen())
    assert chess.Move.from_uci(result["uci"]) in board.legal_moves
    assert result["source"] == "paulsen_style_engine"


@pytest.mark.asyncio
async def test_paulsen_api_move_endpoint():
    """Check the REST endpoints /api/v1/bots/list and /api/v1/bots/move for a game against Paulsen."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        list_resp = await client.get("/api/v1/bots/list")
        assert list_resp.status_code == 200
        bot_ids = [b["id"] for b in list_resp.json()["bots"]]
        assert "paulsen" in bot_ids

        move_resp = await client.post(
            "/api/v1/bots/move",
            json={"bot_id": "paulsen", "fen": chess.STARTING_FEN},
        )
        assert move_resp.status_code == 200
        data = move_resp.json()
        assert data["bot_id"] == "paulsen"
        assert data["source"] == "opening_book"
