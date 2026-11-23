# --- FILE: tests/test_time_machine_play.py ---
"""
A player's game against a past master in the "Time Machine": saving through the same /bots/save-game as the
client does. The master's name in PGN is "Surname, Name": the player-name rules do not apply to it.

Before 17.11 there were no such tests: results in tests were set by the service directly, while the server
rejected the real request (400 username_invalid_chars) - the player's game against a master was not recorded
and the tournament did not advance.
"""

import pytest

from src.api.bots import BotGameSaveRequest, _resolve_personality_for_save
from src.services.bots.guests import GUESTS, GUESTS_BY_ID

API = "/api/v1/tournaments"
SAVE = "/api/v1/bots/save-game"
FOOLS_MATE = ["f2f3", "e7e5", "g2g4", "d8h4"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def my_game(t):
    """The player's first unplayed game of the current round, their colour and the opponent."""
    me = t["my_seat"]
    game = next(g for g in t["games"] if g["round"] == t["current_round"] and g["result"] is None
                and me in (g["white_seat"], g["black_seat"]))
    color = "white" if game["white_seat"] == me else "black"
    opponent_seat = game["black_seat"] if color == "white" else game["white_seat"]
    return game, color, next(p for p in t["players"] if p["seat"] == opponent_seat)


def master_event(client, token) -> tuple[dict, dict, str, dict]:
    """A historical tournament where the player's first opponent is a past master (not a historical bot)."""
    for key in ("avro_1938", "nottingham_1936", "kyiv_1903", "hastings_1895"):
        t = client.post(f"{API}/time-machine/{key}", json={}, headers=auth(token)).json()
        game, color, opponent = my_game(t)
        if opponent["kind"] == "personality":
            return t, game, color, opponent
        assert client.post(f"{API}/{t['id']}/withdraw", headers=auth(token)).status_code == 200
    raise AssertionError("no event starts with a master of the past")


def test_players_game_against_a_master_of_the_past_is_saved(client, token_user_1, published_simulations):
    t, game, color, opponent = master_event(client, token_user_1)
    guest = GUESTS_BY_ID[opponent["bot_key"].removeprefix("guest:")]
    assert opponent["personality_name"] == guest.pgn_name and ", " in guest.pgn_name

    started = client.post(f"{API}/{t['id']}/games/{game['id']}/start", headers=auth(token_user_1))
    assert started.status_code == 200, started.text
    # The client saves the game under the master's Latin name (CustomOpponent.savedName).
    saved = client.post(SAVE, headers=auth(token_user_1), json={
        "bot_id": "custom", "personality_name": guest.pgn_name, "player_color": color, "result": "0-1",
        "moves_uci": FOOLS_MATE, "base_time_ms": game["base_time_ms"], "increment_ms": game["increment_ms"],
        "tournament_game_id": game["id"],
    })
    assert saved.status_code == 200, saved.text
    state = client.get(f"{API}/{t['id']}", headers=auth(token_user_1)).json()
    recorded = next(g for g in state["games"] if g["id"] == game["id"])
    assert recorded["result"] == "0-1" and recorded["game_id"] == saved.json()["game_id"]

    # In the player's archive the opponent appears under the master's name, with his rating in PGN.
    pgn = client.get(f"/api/v1/profile/games/{saved.json()['game_id']}/pgn", headers=auth(token_user_1))
    assert pgn.status_code == 200 and guest.pgn_name in pgn.text and str(guest.rating) in pgn.text, pgn.text[:300]


async def test_every_master_is_accepted_as_the_saved_opponent():
    """The server accepts any master's name (with a comma, spaces and dots) and returns his rating from the registry."""
    for guest in GUESTS:
        payload = BotGameSaveRequest(bot_id="custom", personality_name=guest.pgn_name, player_color="white",
                                     result="1-0", moves_uci=["e2e4"])
        # No database query is needed for a master: name and strength come from the registry.
        assert await _resolve_personality_for_save(None, None, payload) == (guest.pgn_name, guest.rating), guest.id  # type: ignore[arg-type]


async def test_a_name_with_a_comma_that_is_not_a_master_is_still_rejected():
    from src.core.errors import ApiError

    payload = BotGameSaveRequest(bot_id="custom", personality_name="Nobody, At All", player_color="white",
                                 result="1-0", moves_uci=["e2e4"])
    with pytest.raises(ApiError) as caught:
        await _resolve_personality_for_save(None, None, payload)  # type: ignore[arg-type]
    assert caught.value.status_code == 400


SCHOLARS_MATE = ["e2e4", "e7e5", "d1h5", "b8c6", "f1c4", "g8f6", "h5f7"]  # mate to Black: White wins


def test_knockout_win_against_a_master_takes_the_player_to_the_next_round(client, token_user_1, published_simulations):
    """London 1851 knockout: a player's win over a master, sent by a real request, takes him forward."""
    headers = auth(token_user_1)
    t = client.post(f"{API}/time-machine/london_1851", json={}, headers=headers).json()
    assert (t["format"], t["size"], t["current_round"]) == ("knockout", 17, 1)
    game, color, opponent = my_game(t)
    # The novice is the lowest seed: he plays the only play-in match of the first round, and his opponent is a past master.
    assert len(t["games"]) == 1 and opponent["kind"] == "personality"
    guest = GUESTS_BY_ID[opponent["bot_key"].removeprefix("guest:")]

    assert client.post(f"{API}/{t['id']}/games/{game['id']}/start", headers=headers).status_code == 200
    moves, result = (SCHOLARS_MATE, "1-0") if color == "white" else (FOOLS_MATE, "0-1")
    saved = client.post(SAVE, headers=headers, json={
        "bot_id": "custom", "personality_name": guest.pgn_name, "player_color": color, "result": result,
        "moves_uci": moves, "base_time_ms": game["base_time_ms"], "increment_ms": game["increment_ms"],
        "tournament_game_id": game["id"],
    })
    assert saved.status_code == 200, saved.text

    state = client.get(f"{API}/{t['id']}", headers=headers).json()
    assert next(g for g in state["games"] if g["id"] == game["id"])["result"] == result
    # The player advanced to the round of sixteen, the master is out; the player has a new game against another opponent.
    assert (state["status"], state["current_round"]) == ("active", 2)
    players = {p["seat"]: p for p in state["players"]}
    assert players[opponent["seat"]]["eliminated_round"] == 1
    assert players[state["my_seat"]]["eliminated_round"] is None
    next_game, _, next_opponent = my_game(state)
    assert next_game["round"] == 2 and next_opponent["seat"] != opponent["seat"]
    assert len([g for g in state["games"] if g["round"] == 2]) == 8


def test_knockout_loss_to_a_master_ends_the_tournament_for_the_player(client, token_user_1, published_simulations):
    headers = auth(token_user_1)
    t = client.post(f"{API}/time-machine/london_1851", json={}, headers=headers).json()
    game, color, opponent = my_game(t)
    guest = GUESTS_BY_ID[opponent["bot_key"].removeprefix("guest:")]
    assert client.post(f"{API}/{t['id']}/games/{game['id']}/start", headers=headers).status_code == 200
    # The player resigns on the very first move: a game without moves, counted as a loss.
    lost = "0-1" if color == "white" else "1-0"
    saved = client.post(SAVE, headers=headers, json={
        "bot_id": "custom", "personality_name": guest.pgn_name, "player_color": color, "result": lost,
        "termination": "resignation", "moves_uci": [], "base_time_ms": game["base_time_ms"],
        "increment_ms": game["increment_ms"], "tournament_game_id": game["id"],
    })
    assert saved.status_code == 200, saved.text
    state = client.get(f"{API}/{t['id']}", headers=headers).json()
    players = {p["seat"]: p for p in state["players"]}
    assert players[state["my_seat"]]["eliminated_round"] == 1
    assert players[opponent["seat"]]["eliminated_round"] is None
    # The tournament continues without the player: from here the masters play among themselves.
    assert not [g for g in state["games"] if g["round"] == state["current_round"] and g["result"] is None
                and state["my_seat"] in (g["white_seat"], g["black_seat"])]
