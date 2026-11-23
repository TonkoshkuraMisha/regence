# --- FILE: src/services/mini_game_rooms.py ---
"""
Network games of the trainer games between humans (task 19.8, remainder; owner's choice of 18.11): a friendly game of two
players in one of the teaching games (pawn war and others) - no rating, no clocks and no entry in the archive.

Why this is separate from PvP games: an ordinary game (game_state, client board on chess.js) understands only chess -
it will not accept a position without kings, and the end of a mini-game (got a pawn through, captured all pawns, brought
the king over) is different. So there is a separate "room" here: the move and result rules are the same as in the game
against a bot (src/services/mini_games.py), the state is a short record in Redis.

* The room is the key minigame:room:{code} (JSON, lives ROOM_TTL_S since the last action). The code is like the challenge link
  (matchmaker.INVITE_CODE_*). The creator chooses a colour (white, black, random), the second player joins by the link.
* The server checks the move by the game rules; only the side whose turn it is moves, and only against the current version
(version):
    a resubmitted move will not be applied twice. Concurrent requests to one room are separated by a short lock
  (key ...:lock, LOCK_TTL_S) - the second one gets mini_room_busy and retries.
* The result comes from the game rules or from resignation. "Once more" is a new room with the same players and swapped
colours; the old one
    records next - the opponent's page moves there by itself.
* The client learns about the opponent's move by polling the room (GET once a second): for a teaching game without clocks
this is
    enough, and the games WebSocket stays reserved for chess.
"""

import json
import random
import secrets
import time

from src.core.errors import DomainError
from src.db import redis as redis_module
from src.models.user import User
from src.services import mini_games as mg
from src.services.matchmaker import INVITE_CODE_ALPHABET, INVITE_CODE_LENGTH

# How long a room lives after the last action (seconds): a forgotten game disappears by itself.
ROOM_TTL_S = 2 * 3600
# How long the room lock is held for the duration of one action (seconds).
LOCK_TTL_S = 5
COLORS = ("white", "black")


def _key(code: str) -> str:
    return f"minigame:room:{code}"


async def _load(code: str) -> dict:
    raw = await redis_module.redis_client.get(_key(code))
    if raw is None:
        raise DomainError("mini_room_not_found")
    return json.loads(raw)


async def _save(room: dict) -> None:
    await redis_module.redis_client.set(_key(room["code"]), json.dumps(room), ex=ROOM_TTL_S)


class _Locked:
    """Room lock for the duration of an action: a second concurrent request gets mini_room_busy."""

    def __init__(self, code: str):
        self.key = f"{_key(code)}:lock"

    async def __aenter__(self):
        if not await redis_module.redis_client.set(self.key, "1", ex=LOCK_TTL_S, nx=True):
            raise DomainError("mini_room_busy")

    async def __aexit__(self, *_):
        await redis_module.redis_client.delete(self.key)


def view(room: dict, user_id: int | None) -> dict:
    """Room for the client: game, position, moves, players, result, requester colour (you: None - spectator/guest)."""
    you = next((color for color in COLORS if user_id is not None and room[f"{color}_id"] == user_id), None)
    keys = ("code", "game_id", "fen", "moves", "result", "reason", "version", "next")
    return {**{k: room.get(k) for k in keys},
            "white": room["white_name"], "black": room["black_name"], "you": you,
            "waiting": room["white_id"] is None or room["black_id"] is None}


def _seat(room: dict, color: str, user: User) -> None:
    room[f"{color}_id"], room[f"{color}_name"] = user.id, user.username


def _new_room(game: mg.MiniGame) -> dict:
    code = "".join(secrets.choice(INVITE_CODE_ALPHABET) for _ in range(INVITE_CODE_LENGTH))
    return {"code": code, "game_id": game.id, "fen": game.fen, "moves": [], "result": None, "reason": None,
            "version": 0, "next": None, "created": time.time(),
            "white_id": None, "white_name": None, "black_id": None, "black_name": None}


async def create(user: User, game_id: str, color: str) -> dict:
    """New room: the creator takes the chosen colour (random - by chance); the other colour waits for a guest by link."""
    game = mg.get_game(game_id)
    room = _new_room(game)
    _seat(room, random.choice(COLORS) if color not in COLORS else color, user)
    await _save(room)
    return view(room, user.id)


async def get(code: str, user_id: int | None) -> dict:
    return view(await _load(code), user_id)


async def join(user: User, code: str) -> dict:
    """Join the room with a free colour. Already a player - just the room; both seats taken - mini_room_full."""
    async with _Locked(code):
        room = await _load(code)
        if user.id in (room["white_id"], room["black_id"]):
            return view(room, user.id)
        free = next((color for color in COLORS if room[f"{color}_id"] is None), None)
        if free is None:
            raise DomainError("mini_room_full")
        _seat(room, free, user)
        await _save(room)
        return view(room, user.id)


def _color_of(room: dict, user: User) -> str:
    color = next((c for c in COLORS if room[f"{c}_id"] == user.id), None)
    if color is None:
        raise DomainError("mini_room_not_player")
    return color


async def move(user: User, code: str, uci: str, version: int) -> dict:
    """
    A player's move by the game rules. Refusals: the game is over (mini_game_over), no opponent yet (mini_room_waiting), not
    their turn (mini_room_not_your_turn), the version is stale - the move was already made (mini_room_stale), the move is
    illegal by the (mini_game_illegal_move).
    """
    async with _Locked(code):
        room = await _load(code)
        color = _color_of(room, user)
        if room["result"]:
            raise DomainError("mini_game_over")
        if room["white_id"] is None or room["black_id"] is None:
            raise DomainError("mini_room_waiting")
        if version != room["version"]:
            raise DomainError("mini_room_stale")
        game = mg.get_game(room["game_id"])
        board = mg.board_of(game, room["fen"])
        if ("white" if board.turn else "black") != color:
            raise DomainError("mini_room_not_your_turn")
        outcome = mg.play(game, board, uci)
        room["fen"], room["version"] = board.fen(), room["version"] + 1
        room["moves"].append(board.peek().uci())
        if outcome:
            room["result"], room["reason"] = outcome, "rules"
        await _save(room)
        return view(room, user.id)


async def resign(user: User, code: str) -> dict:
    """Resignation: the opponent wins. If already over - mini_game_over."""
    async with _Locked(code):
        room = await _load(code)
        color = _color_of(room, user)
        if room["result"]:
            raise DomainError("mini_game_over")
        room["result"], room["reason"] = ("0-1" if color == "white" else "1-0"), "resign"
        room["version"] += 1
        await _save(room)
        return view(room, user.id)


async def rematch(user: User, code: str) -> dict:
    """
    "Once more" after the end: a new room of the same game with the same players, colours swapped; the old
    one gets next, and the opponent moves over by it by themselves.
    A repeated press (own or the opponent's) leads to the already created one.
    """
    async with _Locked(code):
        room = await _load(code)
        _color_of(room, user)
        if room["next"]:
            return view(await _load(room["next"]), user.id)
        if not room["result"]:
            raise DomainError("mini_room_in_progress")
        game = mg.get_game(room["game_id"])
        fresh = _new_room(game)
        for color, other in (("white", "black"), ("black", "white")):
            fresh[f"{color}_id"], fresh[f"{color}_name"] = room[f"{other}_id"], room[f"{other}_name"]
        await _save(fresh)
        room["next"] = fresh["code"]
        await _save(room)
        return view(fresh, user.id)
