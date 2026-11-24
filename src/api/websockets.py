# --- FILE: src/api/websockets.py ---
"""
The WebSocket of games and the lobby (/ws/matchmaking): all player actions during a game and delivery of events to their tabs.

Login - by a one-time ticket (src/api/deps.get_current_user_ws). On connection the player receives a snapshot of their
game in progress, if there is one (_send_active_game_snapshot_if_exists).

Each client message is {"action": name, ...}; the action handler is registered in ACTION_HANDLERS:

* lobby - join_queue, leave_queue, accept_challenge, create_invite, accept_invite;
* spectators and chat - spectate_game, leave_spectate, chat_message;
* game - make_move, abort_game, resign, offer_draw, accept_draw, decline_draw, berserk;
* rematch - offer_rematch, accept_rematch, decline_rematch.

General rules: an action on a game is accepted only from its participant and only in a suitable status
(_participant_game), otherwise it is silently ignored; a refusal with an explanation goes as an error code
(src/core/errors.py).
The database session is opened for one action and released before sending to the network (ActionContext.release_db) - otherwise
a slow client would hold a pool connection. Message frequency is limited by group (WS_RATE_LIMITS: moves, chat,
offers, lobby, other), size - WS_MAX_MESSAGE_CHARS; for a stream of rejected messages (WS_MAX_STRIKES per
WS_STRIKE_WINDOW_S seconds) the connection is closed with code 1013.

Game state and clocks - src/services/game_state.py, game start - src/services/matchmaker.py, broadcast across
several processes and tabs - src/services/connection_manager.py.
"""

import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.api.deps import get_current_user_ws
from src.api.fair_play import remember_player_ip
from src.api.rate_limit import try_consume
from src.core import observability as obs
from src.core.errors import DomainError, error_payload
from src.core.logging_setup import (
    bind_log_context,
    end_log_context,
    new_request_id,
    start_log_context,
    unbind_log_context,
)
from src.db.session import get_session_factory
from src.models.user import User
from src.services import kid_mode, moderation, notifications
from src.services.anticheat import trusted_premove
from src.services.connection_manager import manager
from src.services.game_engine import game_variant, start_fen_of
from src.services.game_state import (
    berserk_fields,
    is_hourglass,
    is_rated_state,
    live_clock_ms,
    pending_draw_offer,
    state_manager,
)
from src.services.matchmaker import MatchmakingError, chess960_start, matchmaker
from src.services.odds import HOURGLASS
from src.services.rating import classify_time_control

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["WebSockets"])


def _compute_live_clocks(state: dict) -> tuple[int, int]:
    """
    The clocks of both sides at the current moment (ms): the game state stores the remainder at the moment of the last move,
    so for the side that is thinking the time elapsed since last_move_at is subtracted (in an "hourglass" game it is also
    added to the waiting side - game_state.live_clock_ms). The lag quota is not taken into account here.
    """
    now_ms = int(time.time() * 1000)
    return max(0, live_clock_ms(state, "white", now_ms)), max(0, live_clock_ms(state, "black", now_ms))


async def _send_active_game_snapshot_if_exists(db: AsyncSession, user: User):
    """
    If the player reconnected during a game in progress, we restore their board and clocks: a match_found event with
    the full game state from Redis (key user:{id}:current_game -> the game state).
    """
    game_id_str = await state_manager.redis.get(f"user:{user.id}:current_game")
    if not game_id_str:
        return

    game_id = int(game_id_str)
    state = await state_manager.get_game_state(game_id)
    if not state or state.get("status") != "in_progress":
        return

    white_id = int(state["white_id"])
    black_id = int(state["black_id"])
    white_user = await db.get(User, white_id)
    black_user = await db.get(User, black_id)
    white_time, black_time = _compute_live_clocks(state)
    category = classify_time_control(int(state.get("base_time_ms", 180000)), int(state.get("increment_ms", 0)))

    payload = {
        "event": "match_found",
        "game_id": game_id,
        "color": "white" if user.id == white_id else "black",
        "opponent_id": black_id if user.id == white_id else white_id,
        "white_username": white_user.username if white_user else "",
        "white_rating": white_user.rating_for(category) if white_user else 1200,
        "black_username": black_user.username if black_user else "",
        "black_rating": black_user.rating_for(category) if black_user else 1200,
        "is_rated": is_rated_state(state),
        "base_time_ms": int(state.get("base_time_ms", 180000)),
        "increment_ms": int(state.get("increment_ms", 0)),
        "white_time_ms": white_time,
        "black_time_ms": black_time,
        "fen": state.get("board_fen"),
        "pgn": state.get("pgn", ""),
        "variant": game_variant(state.get("board_fen"), state.get("pgn", "")),
        "state_version": int(state.get("state_version", 0)),
        # A draw offer made before the reconnection would otherwise vanish from the screen.
        "draw_offer_from": pending_draw_offer(state),
        "hourglass": is_hourglass(state),
        **berserk_fields(state),
    }
    if state.get("arena_id"):
        payload["arena_id"] = int(state["arena_id"])
    await manager.send_personal_message(payload, user.id)


async def create_rematch_game(db: AsyncSession, prev_state: dict, connection_manager=None) -> dict:
    """
    Creates a rematch game with swapped colours (white_id <-> black_id), with the same time control
    and of the same type (rated / casual). A rematch of a Fischer game is also a 960 game with the same setup (colours
    are swapped - that is how the rematch is fair; the default decision 20.11); the setup is taken from the FEN header in the
    game's PGN.
    A rematch of an "hourglass" game is also an "hourglass": the handicap is shared and does not depend on colours.
    The checks of player availability and the game start are in matchmaker.start_pvp_game.
    """
    odds = None
    base_ms = int(prev_state.get("base_time_ms", 180000))
    if game_variant(prev_state.get("board_fen"), prev_state.get("pgn", "")) == "chess960":
        start = start_fen_of(prev_state.get("pgn")) or chess960_start()
        odds = {"start_fen": start, "white_time_ms": base_ms, "black_time_ms": base_ms, "kind": "chess960"}
    elif is_hourglass(prev_state):
        odds = {"white_time_ms": base_ms, "black_time_ms": base_ms, "kind": HOURGLASS, "hourglass": True}
    return await matchmaker.start_pvp_game(
        white_id=int(prev_state["black_id"]),
        black_id=int(prev_state["white_id"]),
        base_time_ms=int(prev_state.get("base_time_ms", 180000)),
        increment_ms=int(prev_state.get("increment_ms", 0)),
        connection_manager=connection_manager,
        db=db,
        is_rated=is_rated_state(prev_state),
        odds=odds,
    )


async def _fresh_current_user(db: AsyncSession, user: User) -> User:
    """
    The user object from authentication is loaded at connection time and does not see changes in the
    rating after games played - we re-read it in the session of the current action.
    """
    return await db.get(User, user.id, populate_existing=True) or user


async def broadcast_to_game_participants_and_spectators(
        game_id: int,
        white_id: int,
        black_id: int,
        payload: dict,
) -> None:
    """Sends an event to both players and to all spectators watching the game."""
    await manager.send_personal_message(payload, white_id)
    await manager.send_personal_message(payload, black_id)
    await manager.broadcast_to_spectators(game_id, payload)


# ---------------------------------------------------------------------------------------
# WebSocket action handlers. Each client action ("action") is a separate function
# registered in ACTION_HANDLERS; the common checks (the game id, its status, the player's
# participation) are collected in _participant_game.
# ---------------------------------------------------------------------------------------


class _Ignore(Exception):
    """The action is silently ignored: invalid input, someone else's game or a game of an unsuitable status."""


@dataclass
class ActionContext:
    """
    The context of one WebSocket action: the player and a short database session. send and error first release the session,
    then
    send the response.
    """
    user: User
    db: AsyncSession

    async def send(self, payload: dict) -> None:
        """A response to the player themselves (to all their tabs); the database connection is released before sending."""
        await self.release_db()
        await manager.send_personal_message(payload, self.user.id)

    async def release_db(self) -> None:
        """
        Ends the session transaction and returns the connection to the pool before network I/O.

        Any read opens a transaction that holds the pool connection until the end of the action -
        including while the response goes to a slow client. Writes in services (finish_game,
        abort_game, ...) commit on their own, so only the read transaction is closed here;
        expire_on_commit=False keeps already loaded objects accessible. If the session
        is needed again, it opens a new transaction by itself.
        """
        if self.db.in_transaction():
            await self.db.commit()

    async def error(self, code: str, **params) -> None:
        """An action refusal: a code from the registry src/core/errors.py and parameters - the text is assembled by the
        client."""
        await self.send({"event": "error", **error_payload(code, **params)})

    async def reject_move(self, res: dict) -> None:
        """
        A refusal of a move (illegal_move, not_your_turn, version_mismatch, game_inactive) together with
        the current position: the client returns it to the board. No text is shown to the player.
        """
        await self.send({
            "event": "error", "reason": res["reason"], "message": res["reason"],
            "fen": res.get("fen"), "pgn": res.get("pgn"), "state_version": res.get("state_version"),
        })


@dataclass
class GameRef:
    """
    The game the action is performed on: id, state and players; broadcast sends an event to both players and
    spectators.
    """
    game_id: int
    state: dict
    white_id: int
    black_id: int

    def opponent_of(self, user_id: int) -> int:
        return self.black_id if user_id == self.white_id else self.white_id

    async def broadcast(self, payload: dict) -> None:
        await broadcast_to_game_participants_and_spectators(self.game_id, self.white_id, self.black_id, payload)


def _int_field(data: dict, key: str, default: int | None = None) -> int:
    """An integer message field; garbage instead of a number is not an "internal error" but ignored input."""
    value = data.get(key, default)
    if value is None or isinstance(value, bool):
        raise _Ignore
    try:
        return int(value)
    except (TypeError, ValueError):
        raise _Ignore from None


def _rated_flag(data: dict) -> bool:
    """The game type from the message: casual only with an explicit rated: false."""
    return data.get("rated") is not False


def _required_game_id(data: dict) -> int:
    """The game id from the message; without it the action is ignored."""
    if not data.get("game_id"):
        raise _Ignore
    return _int_field(data, "game_id")


async def _load_game(data: dict) -> GameRef:
    """
    The game from data["game_id"] by the state in Redis (a lost state is restored from the database); an unknown
    game - the action is ignored. The player's participation is not checked here - see _participant_game.
    """
    gid = _required_game_id(data)
    state = await state_manager.get_game_state(gid)
    if not state:
        raise _Ignore
    return GameRef(gid, state, int(state["white_id"]), int(state["black_id"]))


async def _participant_game(ctx: ActionContext, data: dict, *, in_progress: bool | None) -> GameRef:
    """
    The game from data["game_id"] in which the current user is a player.
    in_progress=True - only one in progress, False - only a finished one, None - any.
    """
    game = await _load_game(data)
    is_active = game.state.get("status") == "in_progress"
    if in_progress is not None and is_active != in_progress:
        raise _Ignore
    if ctx.user.id not in (game.white_id, game.black_id):
        raise _Ignore
    return game


ActionHandler = Callable[[ActionContext, dict], Awaitable[None]]
ACTION_HANDLERS: dict[str, ActionHandler] = {}


def action(name: str):
    """Decorator: registers the function as the handler of action name in ACTION_HANDLERS."""
    def register(handler: ActionHandler) -> ActionHandler:
        ACTION_HANDLERS[name] = handler
        return handler
    return register


# --- Lobby and invitations ---------------------------------------------------------------

@action("join_queue")
async def _join_queue(ctx: ActionContext, data: dict) -> None:
    """
    A lobby challenge: the time control (3+0 by default), the opponent rating bounds and the game type. The player's rating
    is taken fresh from the database, in the category of this control. If a suitable challenge was already waiting, the game
    starts at once
    (match_found is sent to both by matchmaker); otherwise the player gets queue_joined.
    """
    fresh_user = await _fresh_current_user(ctx.db, ctx.user)
    base_time_ms = _int_field(data, "base_time_ms", 180000)
    increment_ms = _int_field(data, "increment_ms", 0)
    category = classify_time_control(base_time_ms, increment_ms)
    matched_game_id = await matchmaker.join_queue(
        fresh_user.id, fresh_user.username, fresh_user.rating_for(category),
        base_time_ms,
        increment_ms,
        min_rating=data.get("min_rating"),
        max_rating=data.get("max_rating"),
        db=ctx.db,
        rated=_rated_flag(data),
    )
    if matched_game_id is None:
        await ctx.send({"event": "queue_joined"})


@action("leave_queue")
async def _leave_queue(ctx: ActionContext, data: dict) -> None:
    """Withdraw one's own challenge from the lobby."""
    await matchmaker.leave_queue(ctx.user.id)
    await ctx.send({"event": "queue_left"})


@action("accept_challenge")
async def _accept_challenge(ctx: ActionContext, data: dict) -> None:
    """Accept the challenge of player target_user_id from the lobby; the game is created and both are notified by
    matchmaker."""
    if not data.get("target_user_id"):
        raise _Ignore
    await matchmaker.accept_challenge(_int_field(data, "target_user_id"), ctx.user.id, manager, state_manager, db=ctx.db)


@action("create_invite")
async def _create_invite(ctx: ActionContext, data: dict) -> None:
    """
    A private invitation by link: the control (3+2 by default), colour, game type, handicap (odds_kind, who gives it)
    and variant (standard or Fischer chess). The invitation code is returned by the invite_created event; the
    invitation itself is stored by matchmaker in Redis.
    """
    fresh_user = await _fresh_current_user(ctx.db, ctx.user)
    base_time_ms = _int_field(data, "base_time_ms", 180000)
    increment_ms = _int_field(data, "increment_ms", 2000)
    invite_data = await matchmaker.create_private_invite(
        user_id=fresh_user.id,
        username=fresh_user.username,
        rating=fresh_user.rating_for(classify_time_control(base_time_ms, increment_ms)),
        base_time_ms=base_time_ms,
        increment_ms=increment_ms,
        color_pref=str(data.get("color_pref", "random")),
        rated=_rated_flag(data),
        odds_kind=str(data.get("odds_kind", "") or ""),
        odds_giver=str(data.get("odds_giver", "creator") or "creator"),
        variant=str(data.get("variant", "standard") or "standard"),
    )
    await ctx.send({"event": "invite_created", **invite_data})


@action("accept_invite")
async def _accept_invite(ctx: ActionContext, data: dict) -> None:
    """Accept a private invitation by code: the game is started by matchmaker.start_game_from_invite."""
    code = str(data.get("code", "")).strip()
    if not code:
        raise _Ignore
    await matchmaker.start_game_from_invite(code, ctx.user.id, manager, db=ctx.db)


# --- Spectators and chat ----------------------------------------------------------------------

@action("spectate_game")
async def _spectate_game(ctx: ActionContext, data: dict) -> None:
    """
    Become a spectator of a game in progress: the player is added to the spectator list and gets spectate_started with the
    current
    position and clocks; afterwards moves, chat and the game result come to them. A finished game - refusal.
    """
    game = await _load_game(data)
    if game.state.get("status") != "in_progress":
        await ctx.error("spectate_unavailable")
        return

    await manager.add_spectator(game.game_id, ctx.user.id)
    white_user = await ctx.db.get(User, game.white_id)
    black_user = await ctx.db.get(User, game.black_id)
    white_time, black_time = _compute_live_clocks(game.state)
    category = classify_time_control(
        int(game.state.get("base_time_ms", 180000)), int(game.state.get("increment_ms", 0)),
    )

    await ctx.send({
        "event": "spectate_started",
        "game_id": game.game_id,
        "white_username": white_user.username if white_user else "",
        "white_rating": white_user.rating_for(category) if white_user else 1200,
        "black_username": black_user.username if black_user else "",
        "black_rating": black_user.rating_for(category) if black_user else 1200,
        "is_rated": is_rated_state(game.state),
        "base_time_ms": int(game.state.get("base_time_ms", 180000)),
        "increment_ms": int(game.state.get("increment_ms", 0)),
        "white_time_ms": white_time,
        "black_time_ms": black_time,
        "fen": game.state.get("board_fen"),
        "pgn": game.state.get("pgn", ""),
        "state_version": int(game.state.get("state_version", 0)),
        "hourglass": is_hourglass(game.state),
        **berserk_fields(game.state),
    })


@action("leave_spectate")
async def _leave_spectate(ctx: ActionContext, data: dict) -> None:
    """Stop watching the game game_id; without an id - all games the player is watching."""
    if data.get("game_id"):
        await manager.remove_spectator(_int_field(data, "game_id"), ctx.user.id)
    else:
        await manager.remove_user_from_all_spectating(ctx.user.id)
    await ctx.send({"event": "spectate_left"})


# Quick chat phrases are forwarded as a code, not as text: each participant sees the phrase in their own language
# (the texts are in the client catalogues). An unknown code is ignored, like an empty message.
CHAT_PRESETS = frozenset({"good_luck", "thanks", "nice_move", "time_trouble"})


@action("chat_message")
async def _chat_message(ctx: ActionContext, data: dict) -> None:
    """
    A message to the game chat: own text (truncated to 140 characters) or a quick phrase code (preset). Only the players of the
    game
    can write; both players and spectators receive the message. The chat is not stored in the database, the insult filter
    (src/services/civility.py) is not applied to it - a message can be reported to a moderator. A player whose chat
    was disabled by a moderator gets the refusal chat_banned. In a game where either player is in kid mode only quick
    phrases pass; free text gets chat_kid_mode (src/services/kid_mode.py).
    """
    preset = data.get("preset")
    raw_text = str(data.get("text", "")).strip()
    if preset is not None:
        if preset not in CHAT_PRESETS:
            raise _Ignore
        raw_text = ""
    elif not raw_text:
        raise _Ignore
    if moderation.chat_banned(await _fresh_current_user(ctx.db, ctx.user)):
        # A moderator disabled chat for the player (task 17.4).
        await ctx.error("chat_banned")
        return
    game = await _load_game(data)
    if ctx.user.id not in (game.white_id, game.black_id):
        # Only players can write to the game chat: spectators (and anyone who knows the game id)
        # must not spam or suggest moves.
        await ctx.error("chat_forbidden")
        return
    if preset is None:
        players = [await ctx.db.get(User, player_id) for player_id in (game.white_id, game.black_id)]
        refusal = kid_mode.free_chat_refusal(players)
        if refusal is not None:
            await ctx.error(refusal)
            return

    await game.broadcast({
        "event": "chat_message",
        "game_id": game.game_id,
        "sender_id": ctx.user.id,
        "sender": ctx.user.username,
        "text": raw_text[:140],
        **({"preset": preset} if preset is not None else {}),
        "timestamp": int(time.time() * 1000),
    })


# --- Ending a game: abort, resignation, draw --------------------------------------------

@action("abort_game")
async def _abort_game(ctx: ActionContext, data: dict) -> None:
    """
    Aborting a game without a rating change - while fewer than two plies have been made (state_manager.abort_game), otherwise
    the refusal abort_too_late. An arena game cannot be aborted.
    """
    game = await _participant_game(ctx, data, in_progress=True)
    # An arena game is not aborted at will (33.1): otherwise an inconvenient opponent could be "skipped";
    # a no-show is counted by the first-move timeout.
    from src.services import arena as arena_service
    if await arena_service.is_arena_game(ctx.db, game.game_id):
        await ctx.error("arena_no_abort")
        return
    abort_res = await state_manager.abort_game(ctx.db, game.game_id)
    if abort_res.get("status") == "error":
        await ctx.error(abort_res.get("code", "game_not_in_progress"))
        return

    await game.broadcast({
        "event": "game_over",
        "game_id": game.game_id,
        "reason": "aborted",
        "result": "*",
        "white_delta": 0,
        "black_delta": 0,
        "white_new_rating": abort_res["white_new_rating"],
        "black_new_rating": abort_res["black_new_rating"],
    })


@action("berserk")
async def _berserk(ctx: ActionContext, data: dict) -> None:
    """"Berserk" in an arena game (33.3): half the time without increment for an extra point - before one's own first move."""
    game = await _participant_game(ctx, data, in_progress=True)
    from src.services import arena as arena_service
    try:
        res = await arena_service.berserk(ctx.db, game.game_id, ctx.user.id)
    except DomainError as exc:
        await ctx.error(exc.code)
        return
    if res is None:
        return
    await ctx.release_db()
    white_time, black_time = _compute_live_clocks(res["state"])
    await game.broadcast({
        "event": "berserk",
        "game_id": game.game_id,
        "color": res["color"],
        "white_time_ms": white_time,
        "black_time_ms": black_time,
        **berserk_fields(res["state"]),
    })


@action("resign")
async def _resign(ctx: ActionContext, data: dict) -> None:
    """
    Resignation: a win for the opponent. Only one claimant can end the game (claim_game_end) - if mate, a flag or a draw
    ended it at the same moment, the resignation changes nothing. The result and rating are written by finish_game.
    """
    game = await _participant_game(ctx, data, in_progress=True)
    game_result = "0-1" if ctx.user.id == game.white_id else "1-0"
    if not await state_manager.claim_game_end(game.game_id, game_result, "resignation"):
        return  # the game has already been ended by another handler (mate, flag, draw) - it broadcast the result

    rating_updates = await state_manager.finish_game(ctx.db, game.game_id, game_result, termination="resignation")
    await game.broadcast({
        "event": "game_over",
        "game_id": game.game_id,
        "reason": "resignation",
        "winner_id": game.opponent_of(ctx.user.id),
        "result": game_result,
        **rating_updates,
    })


@action("offer_draw")
async def _offer_draw(ctx: ActionContext, data: dict) -> None:
    """Offer a draw: the offer is written to the game state (the draw_offer field) and goes to the opponent."""
    game = await _participant_game(ctx, data, in_progress=True)
    # One offer per position: a repeat (or one after a refusal) - only after the next move.
    # Otherwise draw offers turn into a way of harassing the opponent in time trouble.
    version = str(game.state.get("state_version", 0))
    offered_key = f"draw_offered_at_{ctx.user.id}"
    if str(game.state.get(offered_key, "")) == version:
        await ctx.error("draw_offer_too_soon")
        return
    # Atomically and only while the game is in progress: an ordinary hset after the end would recreate
    # a stub of the state in Redis without players.
    if await state_manager.update_if_in_progress(
            game.game_id, {"draw_offer": str(ctx.user.id), offered_key: version},
    ) is None:
        raise _Ignore
    await manager.send_personal_message(
        {"event": "draw_offered", "game_id": game.game_id, "player_id": ctx.user.id},
        game.opponent_of(ctx.user.id),
    )


@action("accept_draw")
async def _accept_draw(ctx: ActionContext, data: dict) -> None:
    """
    Accept a draw offered by the opponent. The presence of the offer is re-checked atomically when the game ends
    (the guard in claim_game_end): if by that moment there is no offer any more (a reply move and a refusal remove it),
    the game continues.
    """
    game = await _participant_game(ctx, data, in_progress=True)
    draw_offer = str(game.state.get("draw_offer") or "")
    if not draw_offer.isdigit() or int(draw_offer) == ctx.user.id:
        await ctx.error("no_draw_offer")
        return

    def _draw_offer_still_valid(fresh: dict, acceptor_id: int = ctx.user.id) -> bool:
        offer = str(fresh.get("draw_offer") or "")
        return offer.isdigit() and int(offer) != acceptor_id

    game_result = "1/2-1/2"
    if not await state_manager.claim_game_end(game.game_id, game_result, "agreement", guard=_draw_offer_still_valid):
        return

    rating_updates = await state_manager.finish_game(ctx.db, game.game_id, game_result, termination="agreement")
    await game.broadcast({
        "event": "game_over",
        "game_id": game.game_id,
        "reason": "draw_agreement",
        "result": game_result,
        **rating_updates,
    })


@action("decline_draw")
async def _decline_draw(ctx: ActionContext, data: dict) -> None:
    """Decline the opponent's draw: the offer is erased from the game state, the opponent gets draw_declined."""
    game = await _participant_game(ctx, data, in_progress=True)
    if pending_draw_offer(game.state) in (None, ctx.user.id):
        raise _Ignore  # nothing to decline: there is no offer or it is one's own
    if await state_manager.update_if_in_progress(game.game_id, {"draw_offer": ""}) is None:
        raise _Ignore
    await manager.send_personal_message(
        {"event": "draw_declined", "game_id": game.game_id, "player_id": ctx.user.id},
        game.opponent_of(ctx.user.id),
    )


# --- Rematch -----------------------------------------------------------------------------

@action("offer_rematch")
async def _offer_rematch(ctx: ActionContext, data: dict) -> None:
    """Offer a rematch after a finished game: a mark in its state, an event and a notification to the opponent."""
    game = await _participant_game(ctx, data, in_progress=False)
    await state_manager.update_game_state(game.game_id, {"rematch_offer": str(ctx.user.id)})
    opponent = game.opponent_of(ctx.user.id)
    # The notification centre (17.1): the opponent may have left the game page - the rematch will remain in the bell.
    notification = await notifications.record(ctx.db, opponent, "rematch",
                                              {"from": ctx.user.username, "game_id": game.game_id})
    await ctx.release_db()
    await manager.send_personal_message(
        {"event": "rematch_offered", "game_id": game.game_id, "player_id": ctx.user.id}, opponent,
    )
    await notifications.deliver(opponent, notification)


@action("accept_rematch")
async def _accept_rematch(ctx: ActionContext, data: dict) -> None:
    """Accept the opponent's rematch: a new game with swapped colours, the same control and type (create_rematch_game)."""
    game = await _participant_game(ctx, data, in_progress=False)
    rematch_offer = str(game.state.get("rematch_offer") or "")
    if not rematch_offer.isdigit() or int(rematch_offer) == ctx.user.id:
        await ctx.error("no_rematch_offer")
        return

    # Both players are notified inside start_pvp_game. If someone has already started another game,
    # MatchmakingError is raised, and the rematch offer remains valid.
    await create_rematch_game(ctx.db, game.state, connection_manager=manager)
    await state_manager.update_game_state(game.game_id, {"rematch_offer": ""})


@action("decline_rematch")
async def _decline_rematch(ctx: ActionContext, data: dict) -> None:
    """Decline (or withdraw one's own) rematch offer: the mark is erased, the opponent gets rematch_declined."""
    game = await _participant_game(ctx, data, in_progress=None)
    await state_manager.update_game_state(game.game_id, {"rematch_offer": ""})
    await manager.send_personal_message(
        {"event": "rematch_declined", "game_id": game.game_id, "player_id": ctx.user.id},
        game.opponent_of(ctx.user.id),
    )


# --- Move ----------------------------------------------------------------------------------

def _move_payload(ctx: ActionContext, gid: int, command_id: str, res: dict, move_data: dict, game_over: bool) -> dict:
    """The move_made event for players and spectators: the move, the new position and the game record, clocks, the state
    version."""
    return {
        "event": "move_made",
        "game_id": gid,
        "player_id": ctx.user.id,
        "command_id": command_id,
        "state_version": res.get("state_version", 0),
        "move": move_data["uci"],
        "san": move_data["san"],
        "fen": move_data["new_fen"],
        "pgn": move_data["new_pgn"],
        "white_time_ms": res["white_time_ms"],
        "black_time_ms": res["black_time_ms"],
        "game_over": game_over,
    }


async def _record_applied_move(
        ctx: ActionContext, gid: int, data: dict, res: dict, move_data: dict, move_str: str,
) -> None:
    """
    Telemetry and the copy of the state in the DB for an already applied move.

    By this point the move is fixed in Redis and cannot be undone, so a failure here must not
    interfere with broadcasting move_made: otherwise the opponent would not learn about the move, and the mover would get
    an "internal error" although the move is counted.

    Telemetry accumulates in the Redis list game:{id}:moves and is moved to the moves table when the game ends. The time
    per move is by the server clock; the time named by the client goes only into the network delay estimate (network_lag_ms).
    The move_number field records the game's move number (fullmove), not the ply number.
    """
    server_elapsed_ms = res.get("elapsed_ms", 0)
    try:
        client_time_ms = int(data.get("time_taken_ms", server_elapsed_ms))
    except (TypeError, ValueError):
        client_time_ms = server_elapsed_ms
    try:
        await state_manager.save_move_telemetry(gid, {
            "player_id": ctx.user.id,
            "move_number": move_data.get("fullmove_number", 1),
            "notation": move_data.get("uci", move_str),
            "san": move_data.get("san", move_str),
            "fen_after": move_data.get("new_fen", ""),
            "time_taken_ms": server_elapsed_ms,
            "window_blurred_before_move": bool(data.get("window_blurred", False)),
            "is_premove": trusted_premove(data.get("is_premove", False), server_elapsed_ms),
            "network_lag_ms": max(0, server_elapsed_ms - client_time_ms),
        })
    except Exception:
        logger.exception("Could not save move telemetry for game %s", gid)
    try:
        await state_manager.sync_authoritative_state_to_db(ctx.db, gid, res)
    except Exception:
        logger.exception("Could not sync game %s to the database after a move", gid)
        try:
            await ctx.db.rollback()
        except Exception:
            logger.debug("Rollback after failed sync of game %s also failed", gid)


@action("make_move")
async def _make_move(ctx: ActionContext, data: dict) -> None:
    """
    A move in a game. The turn order, the state version, legality and clocks are checked and applied atomically by
    state_manager.process_atomic_move (Redis); a repeat of the same command_id is applied once. A refusal returns
    the current position to the player. The applied move is broadcast to both players and spectators (move_made); if it ended
    the game (mate, stalemate, a draw by the rules) or a fallen flag was found on a move attempt - the result is written by
    finish_game and
    broadcast as game_over.
    """
    move_str = data.get("move")
    if not move_str or not isinstance(move_str, str) or len(move_str) > 10:
        raise _Ignore
    gid = _required_game_id(data)
    command_id = str(data.get("command_id") or uuid.uuid4().hex)[:64]
    expected_version = data.get("state_version")
    if isinstance(expected_version, bool) or not isinstance(expected_version, int):
        expected_version = None

    # Thinking time by the client's clock - for the lag quota (33.3); garbage instead of a number - no time is returned.
    client_elapsed_ms = data.get("time_taken_ms")
    if isinstance(client_elapsed_ms, bool) or not isinstance(client_elapsed_ms, int | float) or client_elapsed_ms < 0:
        client_elapsed_ms = None

    res = await state_manager.process_atomic_move(
        game_id=gid,
        user_id=ctx.user.id,
        command_id=command_id,
        move_str=move_str,
        expected_version=expected_version,
        client_elapsed_ms=int(client_elapsed_ms) if client_elapsed_ms is not None else None,
    )
    if res["status"] == "ignored":
        return
    if res["status"] == "error":
        await ctx.reject_move(res)
        return

    game = GameRef(gid, {}, res["white_id"], res["black_id"])
    move_data: dict = res.get("move_data") or {}

    if move_data:
        await _record_applied_move(ctx, gid, data, res, move_data, move_str)

    if res["status"] == "success":
        await game.broadcast(_move_payload(ctx, gid, command_id, res, move_data, game_over=False))
        return

    # game_over: mate/stalemate/a draw by the rules - or a flag detected on a move attempt.
    game_result, termination = res["result"], res["termination"]
    try:
        rating_updates = await state_manager.finish_game(
            ctx.db, gid, game_result, termination=termination,
            final_pgn=move_data["new_pgn"] if move_data else None,
        )
    except Exception:
        # The result will be added by the reconciliation (reconcile_unfinished_games), which will also broadcast game_over, but
        # the last move has already been made - the opponent must see it now, not a "stuck" board.
        if move_data:
            await game.broadcast(_move_payload(ctx, gid, command_id, res, move_data, game_over=False))
        raise
    if move_data:
        await game.broadcast({
            **_move_payload(ctx, gid, command_id, res, move_data, game_over=True),
            "result": game_result,
            **rating_updates,
        })
    await game.broadcast({
        "event": "game_over",
        "game_id": gid,
        "reason": termination,
        "result": game_result,
        "white_time_ms": res["white_time_ms"],
        "black_time_ms": res["black_time_ms"],
        **rating_updates,
    })


# ---------------------------------------------------------------------------------------


async def _dispatch_action(
        session_factory: async_sessionmaker[AsyncSession],
        user: User,
        action_name: str,
        handler: ActionHandler,
        data: dict,
) -> None:
    """
    Performs one action in its own short DB session.

    The session is closed right after the action and the connection returns to the pool. One session for
    the whole WebSocket connection would keep a transaction open while the player is connected: with a couple of
    dozen players in the lobby the pool would run out and all DB requests would time out.
    """
    start = time.perf_counter()
    outcome = obs.OUTCOME_OK
    # Log context: the game the action refers to (game_id in the message) - all lines of the action carry it.
    game_id = data.get("game_id")
    bind_log_context(game_id=game_id if isinstance(game_id, int) else None, action=action_name)
    async with session_factory() as db:
        ctx = ActionContext(user=user, db=db)
        try:
            await handler(ctx, data)
        except _Ignore:
            outcome = obs.OUTCOME_IGNORED
        except MatchmakingError as mm_err:
            outcome = obs.OUTCOME_REJECTED
            await ctx.error(mm_err.code, **mm_err.params)
        except Exception:
            outcome = obs.OUTCOME_ERROR
            logger.exception("Error processing WS action '%s' for user %s", action_name, user.id)
            await ctx.error("internal_error")
    # action_name is a key from ACTION_HANDLERS, i.e. a finite set of label values.
    obs.WS_ACTIONS.labels(action_name, outcome).inc()
    elapsed = time.perf_counter() - start
    obs.WS_ACTION_SECONDS.labels(action_name).observe(elapsed)
    # Each player action leaves a trace: it shows what happened to the game before a failure (a move, a refusal, an error).
    logger.log(logging.WARNING if outcome == obs.OUTCOME_ERROR else logging.INFO, "ws_action",
               extra={"outcome": outcome, "duration_ms": round(elapsed * 1000, 1)})
    unbind_log_context("game_id", "action")


# --- Message rate limiting ------------------------------------------------------
#
# Limits are counted per user (all their tabs and workers together) in Redis, by groups of
# actions: (messages, window in seconds). Moves are limited generously - bullet with premoves must not
# run into the limit - while chat and offers are strict, so that they cannot be used for spam.

WS_MAX_MESSAGE_CHARS = 4096
WS_RATE_LIMITS: dict[str, tuple[int, int]] = {
    "moves": (60, 10),
    "chat": (5, 10),
    "offers": (6, 60),
    "lobby": (20, 10),
    "other": (30, 10),
}
_ACTION_GROUPS = {
    "make_move": "moves",
    "chat_message": "chat",
    "offer_draw": "offers", "offer_rematch": "offers",
    "join_queue": "lobby", "leave_queue": "lobby", "accept_challenge": "lobby",
    "create_invite": "lobby", "accept_invite": "lobby",
}
# A connection that keeps sending messages over the limit is closed: an honest client
# does not accumulate that many rejected messages within WS_STRIKE_WINDOW_S.
WS_MAX_STRIKES = 30
WS_STRIKE_WINDOW_S = 10.0
# The constant is not used here: code 1008 closes a connection on session revocation
# (connection_manager.WS_CLOSE_SESSION_REVOKED) and on a wrong ticket (src/api/deps.py).
WS_CLOSE_POLICY_VIOLATION = 1008
# Flood is closed with code 1013 (try again later), not 1008: the client understands 1008 as
# "session revoked" and logs the player out although their token is fine.
WS_CLOSE_FLOOD = 1013


class _StrikeCounter:
    """The counter of rejected messages of one connection over the last WS_STRIKE_WINDOW_S seconds (in process memory)."""

    def __init__(self):
        self._times: list[float] = []

    def add(self) -> int:
        now = time.monotonic()
        self._times = [t for t in self._times if now - t < WS_STRIKE_WINDOW_S]
        self._times.append(now)
        return len(self._times)


async def _within_rate_limit(user_id: int, action_name: str) -> bool:
    """Whether the action fits the limit of its group (the counter in Redis: ratelimit:ws:<group>:user:<id>:<window>)."""
    group = _ACTION_GROUPS.get(action_name, "other")
    limit, window_s = WS_RATE_LIMITS[group]
    return await try_consume(f"ws:{group}", f"user:{user_id}", limit, window_s)


async def _reject_rate_limited(user: User, action_name: str, data: dict) -> None:
    """The rate_limited refusal to the player; for a move - together with the current position so that the client returns it to
    the board."""
    payload: dict[str, Any] = {"event": "error", "action": action_name, **error_payload("rate_limited")}
    if action_name == "make_move" and data.get("game_id"):
        # The client has already shown the move on the board - we return the current position to it.
        try:
            state = await state_manager.get_game_state(int(data["game_id"]))
        except (TypeError, ValueError):
            state = None
        if state:
            payload.update(
                fen=state.get("board_fen"), pgn=state.get("pgn", ""),
                state_version=int(state.get("state_version", 0)),
            )
    await manager.send_personal_message(payload, user.id)


async def _handle_message(
        session_factory: async_sessionmaker[AsyncSession], user: User, raw: str,
) -> bool:
    """Parses and executes one message. False - the message was rejected (counted towards flood)."""
    if len(raw) > WS_MAX_MESSAGE_CHARS:
        await manager.send_personal_message(
            {"event": "error", **error_payload("message_too_large")}, user.id,
        )
        return False
    try:
        data = json.loads(raw)
    except ValueError:
        return False  # garbage: we send no reply, but count it
    if not isinstance(data, dict):
        return False

    action_name = str(data.get("action") or "")
    handler = ACTION_HANDLERS.get(action_name)
    if handler is None:
        return True  # an unknown action (for example, from a newer client version) - we skip it

    if not await _within_rate_limit(user.id, action_name):
        obs.WS_ACTIONS.labels(action_name, obs.OUTCOME_RATE_LIMITED).inc()
        await _reject_rate_limited(user, action_name, data)
        return False

    await _dispatch_action(session_factory, user, action_name, handler, data)
    return True


@router.websocket("/matchmaking")
async def matchmaking_endpoint(
        websocket: WebSocket,
        current_user: User = Depends(get_current_user_ws),
        session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
):
    """
    A player's connection: registers it, remembers the address (for the fair-play rule), sends a snapshot of the game in
    progress
    and then processes messages one by one while the connection is open. For a stream of rejected messages the connection
    is closed.
    """
    log_token = start_log_context(user_id=current_user.id, channel="ws", ws_id=new_request_id())
    await manager.connect(websocket, current_user.id)
    logger.info("ws_connected")
    # The player's address is needed by the fair-play rule: an engine request without a token from the same address
    # during their game is rejected.
    ws_client = getattr(websocket, "client", None)
    await remember_player_ip(current_user.id, ws_client.host if ws_client else None)
    obs.WS_CONNECTIONS.inc()
    strikes = _StrikeCounter()
    try:
        await manager.send_personal_message(
            {"event": "connected", "message": f"Welcome, {current_user.username}!"}, current_user.id,
        )
        async with session_factory() as db:
            await _send_active_game_snapshot_if_exists(db, current_user)

        while True:
            raw = await websocket.receive_text()
            accepted = await _handle_message(session_factory, current_user, raw)
            if not accepted and strikes.add() >= WS_MAX_STRIKES:
                logger.warning("Closing WebSocket of user %s: message flood", current_user.id)
                await websocket.close(code=WS_CLOSE_FLOOD)
                break

    except WebSocketDisconnect as closed:
        # The close code distinguishes a page reload / tab close (1001, 1005) from a network drop (1006).
        logger.info("ws_disconnected", extra={"close_code": closed.code})
    except Exception:
        logger.exception("WebSocket unexpected error for user %s", current_user.id)
    finally:
        obs.WS_CONNECTIONS.dec()
        # We close only this connection: the user's other tabs stay online.
        await manager.disconnect(current_user.id, websocket)
        end_log_context(log_token)
