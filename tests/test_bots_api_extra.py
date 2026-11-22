# --- FILE: tests/test_bots_api_extra.py ---
"""API ботов: каталог мастеров прошлого, отказы ответа на ничью и итоги сохранения партии (сдача, флаг, ошибки)."""

import pytest

from src.services import move_check

API = "/api/v1/bots"
LATE = "r1bqkb1r/pppp1ppp/2n2n2/4p3/4P3/2N2N2/PPPP1PPP/R1BQKB1R w KQkq - 4 12"
MOVES = ["e2e4", "e7e5", "g1f3", "b8c6"]


def _save(client, token, **fields):
    body = {"bot_id": "philidor", "player_color": "white", "result": "1-0", "moves_uci": MOVES, **fields}
    return client.post(f"{API}/save-game", headers={"Authorization": f"Bearer {token}"}, json=body)


def test_guests_catalog_and_detail(client):
    guests = client.get(f"{API}/guests").json()["guests"]
    assert guests and {"id", "pgn_name", "era", "rating", "events", "openings"} <= set(guests[0])
    assert set(guests[0]["openings"]) == {"white", "black"}
    one = client.get(f"{API}/guests/{guests[0]['id']}").json()
    assert one["id"] == guests[0]["id"] and "config" in one
    assert client.get(f"{API}/guests/nobody").status_code == 404


def test_draw_offer_engine_busy(client, monkeypatch):
    async def busy(board):
        return None

    monkeypatch.setattr(move_check, "evaluate_cached", busy)
    body = {"fen": LATE, "bot_id": "custom", "bot_color": "black", "config": {"draw_attitude": 0}}
    reply = client.post(f"{API}/draw-offer", json=body)
    assert reply.status_code == 503 and reply.headers["Retry-After"] == "5"


@pytest.mark.parametrize("fen, code", [
    ("not a fen", "invalid_fen"),
    ("8/8/8/8/8/8/8/8 w - - 0 1", "invalid_position"),
    ("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1", "game_already_over"),
])
def test_draw_offer_rejects_unplayable_positions(client, fen, code):
    body = {"fen": fen, "bot_id": "morphy", "bot_color": "white"}
    reply = client.post(f"{API}/draw-offer", json=body)
    assert reply.status_code == 400 and code in reply.text


def test_save_game_resignation_is_a_loss_for_the_player(client, token_user_1):
    saved = _save(client, token_user_1, termination="resignation")
    assert saved.status_code == 200, saved.text
    assert saved.json()["result"] == "0-1"


@pytest.mark.parametrize("result", ["1-0", "0-1"])
def test_save_game_timeout_follows_the_standing_flag(client, token_user_1, result):
    # Флаг упал у проигравшей стороны, у победителя хватает материала для мата — итог совпадает с присланным.
    saved = _save(client, token_user_1, termination="timeout", result=result)
    assert saved.status_code == 200, saved.text
    assert saved.json()["result"] == result


def test_save_game_timeout_needs_a_winner(client, token_user_1):
    saved = _save(client, token_user_1, termination="timeout", result="1/2-1/2")
    assert saved.status_code == 400 and "flag_winner_required" in saved.text


def test_save_game_without_termination_on_live_position(client, token_user_1):
    saved = _save(client, token_user_1)
    assert saved.status_code == 400 and "termination_required" in saved.text


def test_save_game_rejects_bad_history(client, token_user_1):
    assert "invalid_history_move" in _save(client, token_user_1, moves_uci=["zzzz"], termination="resignation").text
    assert "illegal_history_move" in _save(client, token_user_1, moves_uci=["e2e5"], termination="resignation").text

