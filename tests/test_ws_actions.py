# --- FILE: tests/test_ws_actions.py ---
"""
WebSocket actions (src/api/websockets.py): refusals and rare handler branches - chat, spectators, cancel, berserk,
resign, draw, rematch, invitations, a move with the game result, snapshot on reconnect. Messages go through
the real matchmaking_endpoint (as in test_ws_rate_limit.py), DB sessions are test ones.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import WebSocketDisconnect

from src.api import websockets as ws_module
from src.api.websockets import matchmaking_endpoint
from src.core.errors import DomainError
from src.db.session import get_session_factory
from src.main import app
from src.models.user import User
from src.services import arena as arena_service
from src.services.game_state import state_manager

_CLOSE = object()


class QueueSocket:
    """WebSocket-WebSocket stub: incoming messages are a queue, outgoing ones are recorded."""

    def __init__(self):
        self.incoming: asyncio.Queue = asyncio.Queue()
        self.sent: list[dict] = []
        self.closed_with: int | None = None

    async def accept(self):
        pass

    async def send_text(self, text: str):
        self.sent.append(json.loads(text))

    async def receive_text(self):
        item = await self.incoming.get()
        if item is _CLOSE:
            raise WebSocketDisconnect(code=1001)
        if isinstance(item, Exception):
            raise item
        return item if isinstance(item, str) else json.dumps(item)

    async def close(self, code: int = 1000):
        self.closed_with = code

    def events(self, event: str) -> list[dict]:
        return [m for m in self.sent if m.get("event") == event]

    def codes(self) -> list[str]:
        return [m["code"] for m in self.events("error") if "code" in m]


async def _run(user: User, messages: list, *, close: bool = True) -> QueueSocket:
    socket = QueueSocket()
    for message in messages:
        socket.incoming.put_nowait(message)
    if close:
        socket.incoming.put_nowait(_CLOSE)
    await asyncio.wait_for(matchmaking_endpoint(socket, user, app.dependency_overrides[get_session_factory]()), timeout=10)
    return socket


@pytest.fixture
async def duo(db_session):
    """Two players in the DB and a running game in Redis (id 7001), plus an outside spectator."""
    users = [User(
        username=f"wa_{i}", hashed_password="pw", bullet_rating=1500, blitz_rating=1500, rapid_rating=1500,
        classical_rating=1500,
    ) for i in range(3)]
    db_session.add_all(users)
    await db_session.commit()
    white, black, watcher = users
    await state_manager.initialize_game(7001, white.id, black.id, 180000, 0)
    return white, black, watcher


GID = 7001


async def test_reconnect_sends_snapshot_with_arena_and_draw_offer(duo):
    white, black, _ = duo
    await state_manager.update_game_state(GID, {"draw_offer": str(black.id), "arena_id": 5})
    socket = await _run(white, [])
    snap = socket.events("match_found")[0]
    assert snap["game_id"] == GID and snap["color"] == "white" and snap["arena_id"] == 5
    assert snap["draw_offer_from"] == black.id
    assert snap["black_username"] == black.username


async def test_no_snapshot_for_finished_game(duo):
    white, _, _ = duo
    await state_manager.update_game_state(GID, {"status": "completed"})
    socket = await _run(white, [])
    assert not socket.events("match_found")


async def test_connection_survives_unexpected_error_in_receive(duo):
    white, _, _ = duo
    socket = QueueSocket()
    socket.incoming.put_nowait(RuntimeError("boom"))
    await asyncio.wait_for(matchmaking_endpoint(socket, white, app.dependency_overrides[get_session_factory]()), timeout=5)
    assert socket.events("connected")


async def test_unknown_action_and_non_dict_are_not_errors(duo):
    white, _, _ = duo
    socket = await _run(white, [{"action": "from_the_future"}])
    assert not socket.events("error")


async def test_handler_crash_becomes_internal_error(duo, monkeypatch):
    white, _, _ = duo

    async def boom(ctx, data):
        raise RuntimeError("bug")

    monkeypatch.setitem(ws_module.ACTION_HANDLERS, "leave_queue", boom)
    socket = await _run(white, [{"action": "leave_queue"}])
    assert socket.codes() == ["internal_error"]


async def test_rate_limited_non_move_gets_plain_error(duo, monkeypatch):
    white, _, _ = duo
    monkeypatch.setitem(ws_module.WS_RATE_LIMITS, "lobby", (1, 60))
    socket = await _run(white, [{"action": "leave_queue"}] * 2)
    assert socket.codes() == ["rate_limited"]
    assert socket.events("error")[0].get("pgn") is None


async def test_rate_limited_move_with_bad_game_id_has_no_position(duo, monkeypatch):
    white, _, _ = duo
    monkeypatch.setitem(ws_module.WS_RATE_LIMITS, "moves", (1, 60))
    first = {"action": "make_move", "game_id": GID, "move": "e2e4"}
    bad = {"action": "make_move", "game_id": "abc", "move": "e2e4"}
    socket = await _run(white, [first, bad])
    assert socket.codes() == ["rate_limited"]
    assert "fen" not in socket.events("error")[0]


# --- Lobby and invitations -----------------------------------------------------------------

async def test_accept_challenge_requires_target_and_reports_matchmaker_error(duo):
    white, black, _ = duo
    socket = await _run(white, [
        {"action": "accept_challenge"},  # without target_user_id - ignored
        {"action": "accept_challenge", "target_user_id": "x"},  # garbage - ignored
        {"action": "accept_challenge", "target_user_id": white.id},  # oneself
    ])
    assert socket.codes() == ["own_challenge"]


async def test_invite_creation_and_acceptance_errors(duo):
    watcher = duo[2]
    socket = await _run(watcher, [
        {"action": "create_invite", "color_pref": "white", "rated": False, "variant": "standard"},
        {"action": "accept_invite", "code": "   "},  # empty code - ignored
        {"action": "accept_invite", "code": "NOSUCH"},
    ])
    created = socket.events("invite_created")[0]
    assert created["color_pref"] == "white" and created["rated"] is False
    assert socket.codes() == ["invite_invalid"]


# --- Spectators ------------------------------------------------------------------------------

async def test_spectate_lifecycle(duo):
    _, _, watcher = duo
    socket = await _run(watcher, [
        {"action": "spectate_game", "game_id": GID},
        {"action": "leave_spectate", "game_id": GID},
        {"action": "spectate_game", "game_id": GID},
        {"action": "leave_spectate"},  # no id - all games
        {"action": "spectate_game", "game_id": 999999},  # unknown - ignored
    ])
    assert len(socket.events("spectate_started")) == 2
    assert len(socket.events("spectate_left")) == 2

    await state_manager.update_game_state(GID, {"status": "completed"})
    socket = await _run(watcher, [{"action": "spectate_game", "game_id": GID}])
    assert socket.codes() == ["spectate_unavailable"]


# --- Chat ----------------------------------------------------------------------------------

async def test_chat_rules(duo, db_session):
    white, _, watcher = duo
    preset = next(iter(ws_module.CHAT_PRESETS))
    socket = await _run(white, [
        {"action": "chat_message", "game_id": GID, "preset": "no-such-preset"},  # ignored
        {"action": "chat_message", "game_id": GID, "text": "   "},  # empty - ignored
        {"action": "chat_message", "game_id": GID, "preset": preset},
    ])
    sent = socket.events("chat_message")
    assert len(sent) == 1 and sent[0]["preset"] == preset and sent[0]["text"] == ""

    outsider = await _run(watcher, [{"action": "chat_message", "game_id": GID, "text": "hi"}])
    assert outsider.codes() == ["chat_forbidden"]

    db_user = await db_session.get(User, white.id)
    db_user.chat_banned_until = datetime.now(UTC) + timedelta(days=1)
    await db_session.commit()
    banned = await _run(white, [{"action": "chat_message", "game_id": GID, "text": "hi"}])
    assert banned.codes() == ["chat_banned"]


async def test_chat_with_a_kid_takes_only_quick_phrases(duo, db_session):
    """Kid mode (task 23.1): in a game with a kid neither side sends free text; quick phrases still go through."""
    white, black, _ = duo
    kid = await db_session.get(User, black.id)
    kid.kid_mode = True
    await db_session.commit()
    preset = next(iter(ws_module.CHAT_PRESETS))
    socket = await _run(white, [
        {"action": "chat_message", "game_id": GID, "text": "hello"},
        {"action": "chat_message", "game_id": GID, "preset": preset},
    ])
    assert socket.codes() == ["chat_kid_mode"]
    sent = socket.events("chat_message")
    assert len(sent) == 1 and sent[0]["preset"] == preset


# --- Cancel, berserk ----------------------------------------------------------------------

async def test_abort_branches(duo, monkeypatch):
    white, _, _ = duo

    async def arena_game(db, gid):
        return True

    monkeypatch.setattr(arena_service, "is_arena_game", arena_game)
    socket = await _run(white, [{"action": "abort_game", "game_id": GID}])
    assert socket.codes() == ["arena_no_abort"]

    async def regular(db, gid):
        return False

    monkeypatch.setattr(arena_service, "is_arena_game", regular)
    await state_manager.update_game_state(GID, {"state_version": 3})
    socket = await _run(white, [{"action": "abort_game", "game_id": GID}])
    assert socket.codes() == ["abort_too_late"]


async def test_berserk_branches(duo, monkeypatch):
    white, _, _ = duo
    outcomes = iter([DomainError("berserk_unavailable"), None])

    async def fake_berserk(db, gid, uid):
        out = next(outcomes)
        if isinstance(out, Exception):
            raise out
        return out

    monkeypatch.setattr(arena_service, "berserk", fake_berserk)
    socket = await _run(white, [{"action": "berserk", "game_id": GID}] * 2)
    assert socket.codes() == ["berserk_unavailable"]
    assert not socket.events("berserk")  # repeated berserk - silence

    async def ok(db, gid, uid):
        return {"color": "white", "state": await state_manager.get_game_state(gid)}

    monkeypatch.setattr(arena_service, "berserk", ok)
    socket = await _run(white, [{"action": "berserk", "game_id": GID}])
    assert socket.events("berserk")[0]["color"] == "white"


# --- Resign and draw ------------------------------------------------------------------------

async def test_resign_loses_race_to_other_ending(duo, monkeypatch):
    white, _, _ = duo

    async def lost(*args, **kwargs):
        return False

    monkeypatch.setattr(state_manager, "claim_game_end", lost)
    socket = await _run(white, [{"action": "resign", "game_id": GID}])
    assert not socket.events("game_over") and not socket.codes()


async def test_draw_offer_flow_and_refusals(duo, monkeypatch):
    white, black, _ = duo
    # nothing to accept
    socket = await _run(white, [{"action": "accept_draw", "game_id": GID}])
    assert socket.codes() == ["no_draw_offer"]
    # nothing to decline - ignored
    socket = await _run(white, [{"action": "decline_draw", "game_id": GID}])
    assert not socket.events("error")

    # one's own offer cannot be accepted; the opponent declines it
    await _run(white, [{"action": "offer_draw", "game_id": GID}])
    socket = await _run(white, [{"action": "accept_draw", "game_id": GID}])
    assert socket.codes() == ["no_draw_offer"]
    assert not (await _run(white, [{"action": "decline_draw", "game_id": GID}])).events("error")
    await _run(black, [{"action": "decline_draw", "game_id": GID}])
    assert not (await state_manager.get_game_state(GID)).get("draw_offer")

    # draw accepted, but the offer vanished before the claim - the game continues
    await state_manager.update_game_state(GID, {"draw_offer": str(black.id)})

    async def lost(*args, **kwargs):
        return False

    monkeypatch.setattr(state_manager, "claim_game_end", lost)
    socket = await _run(white, [{"action": "accept_draw", "game_id": GID}])
    assert not socket.events("game_over")


async def test_draw_offer_after_game_ended_is_ignored(duo, monkeypatch):
    white, _, _ = duo

    async def ended(*args, **kwargs):
        return None

    monkeypatch.setattr(state_manager, "update_if_in_progress", ended)
    socket = await _run(white, [{"action": "offer_draw", "game_id": GID}, {"action": "decline_draw", "game_id": GID}])
    assert not socket.events("draw_offered") and not socket.codes()


# --- Rematch -------------------------------------------------------------------------------

async def test_rematch_flow(duo):
    white, black, _ = duo
    await state_manager.update_game_state(GID, {"status": "completed"})
    socket = await _run(black, [{"action": "accept_rematch", "game_id": GID}])
    assert socket.codes() == ["no_rematch_offer"]

    await _run(white, [{"action": "offer_rematch", "game_id": GID}])
    assert (await state_manager.get_game_state(GID))["rematch_offer"] == str(white.id)
    # one's own offer cannot be accepted
    assert (await _run(white, [{"action": "accept_rematch", "game_id": GID}])).codes() == ["no_rematch_offer"]

    declined = await _run(black, [{"action": "decline_rematch", "game_id": GID}])
    assert not declined.codes()
    assert not (await state_manager.get_game_state(GID)).get("rematch_offer")

    # an accepted offer creates a game with swapped colors
    await _run(white, [{"action": "offer_rematch", "game_id": GID}])
    accepted = await _run(black, [{"action": "accept_rematch", "game_id": GID}])
    started = accepted.events("match_found")
    assert started and started[-1]["color"] == "white"  # Black from the previous game is now White


async def test_create_rematch_for_chess960_and_hourglass(duo, monkeypatch):
    white, black, db = duo[0], duo[1], None
    from src.services import matchmaker as mm_module

    captured: list[dict] = []

    async def fake_start(**kwargs):
        captured.append(kwargs)
        return {"game_id": 1}

    monkeypatch.setattr(mm_module.matchmaker, "start_pvp_game", fake_start)
    monkeypatch.setattr(ws_module, "game_variant", lambda fen, pgn: "chess960")
    monkeypatch.setattr(ws_module, "start_fen_of", lambda pgn: None)
    prev = {"white_id": str(white.id), "black_id": str(black.id), "base_time_ms": "60000", "increment_ms": "0"}
    await ws_module.create_rematch_game(db, prev)
    assert captured[0]["odds"]["kind"] == "chess960" and captured[0]["white_id"] == black.id

    monkeypatch.setattr(ws_module, "game_variant", lambda fen, pgn: "standard")
    monkeypatch.setattr(ws_module, "is_hourglass", lambda state: True)
    await ws_module.create_rematch_game(db, prev)
    assert captured[1]["odds"]["hourglass"] is True


# --- Moves ---------------------------------------------------------------------------------

async def test_move_input_validation_and_error_replies(duo):
    white, black, _ = duo
    socket = await _run(white, [
        {"action": "make_move", "game_id": GID},  # no move - ignored
        {"action": "make_move", "game_id": GID, "move": "e2e4e4e4e4e4"},  # too long - ignored
        {"action": "make_move", "game_id": GID, "move": 5},  # not a string - ignored
        {"action": "make_move", "game_id": True, "move": "e2e4"},  # bool bool instead of an id - ignored
        {"action": "make_move", "game_id": GID, "move": "e2e5", "state_version": True, "time_taken_ms": -5},
    ])
    errors = socket.events("error")
    assert len(errors) == 1 and "fen" in errors[0]  # illegal_move illegal_move returns the position

    # repeating a command with the same command_id - silence
    move = {"action": "make_move", "game_id": GID, "move": "e2e4", "command_id": "c1", "time_taken_ms": 12.5}
    socket = await _run(white, [move, move])
    assert len(socket.events("move_made")) == 1


async def test_move_survives_telemetry_and_sync_failures(duo, monkeypatch):
    white, _, _ = duo

    async def boom(*args, **kwargs):
        raise RuntimeError("redis/db hiccup")

    monkeypatch.setattr(state_manager, "save_move_telemetry", boom)
    monkeypatch.setattr(state_manager, "sync_authoritative_state_to_db", boom)
    socket = await _run(white, [{"action": "make_move", "game_id": GID, "move": "e2e4"}])
    assert len(socket.events("move_made")) == 1


async def test_checkmate_finishes_game_and_failed_finish_still_shows_last_move(duo, monkeypatch, db_session):
    white, black, _ = duo
    from src.models.game import Game, GameStatus

    # The game must be in the DB for finish_game; the position is mate in one (Ra8#).
    fen = "6k1/5ppp/8/8/8/8/8/R6K w - - 0 1"
    game = Game(id=7002, white_player_id=white.id, black_player_id=black.id, status=GameStatus.IN_PROGRESS,
                base_time_ms=180000, increment_ms=0, board_fen=fen, initial_fen=fen)
    db_session.add(game)
    await db_session.commit()
    await state_manager.initialize_game(7002, white.id, black.id, 180000, 0, start_fen=fen)

    socket = await _run(white, [{"action": "make_move", "game_id": 7002, "move": "a1a8"}])
    assert socket.events("game_over")[0]["reason"] in ("checkmate", "mate")

    # finish_game failed: the last move is still broadcast, the error goes to internal_error
    game2 = Game(id=7003, white_player_id=white.id, black_player_id=black.id, status=GameStatus.IN_PROGRESS,
                 base_time_ms=180000, increment_ms=0, board_fen=fen, initial_fen=fen)
    db_session.add(game2)
    await db_session.commit()
    await state_manager.initialize_game(7003, white.id, black.id, 180000, 0, start_fen=fen)

    async def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(state_manager, "finish_game", boom)
    socket = await _run(white, [{"action": "make_move", "game_id": 7003, "move": "a1a8"}])
    assert socket.events("move_made") and socket.codes() == ["internal_error"]
