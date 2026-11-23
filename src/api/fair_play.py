# --- FILE: src/api/fair_play.py ---
"""
Fair play: engine hints are unavailable while the player has a game with a human in progress - rated or casual
(a human sits on the other side, and a hint against them is unfair in both cases).

The dependency `forbid_engine_help_during_game` is attached to all endpoints that give out
a position evaluation or an engine move: /analysis/position, /tablebase, /find-mate, /opening-explorer, /advice, /hint,
/check-move; /bots/move, /bots/custom-move, /bots/draw-offer; /chess960/move and /bot-move;
/repertoires/{id}/opponent; import and review of one's own games (/imports/*). The check is on the server: hiding the button in
the interface is not enough, the endpoint can be called directly.

Where the data comes from (all in Redis): the player's game in progress - key user:{id}:current_game (written by
src/services/game_state.py); player addresses - sets fairplay:ip:{address} with the ids of players who connected
from this address by WebSocket during the last PLAYER_IP_TTL_S; anti-cheat signals - counters
fairplay:engine_requests:{game id}:{player id} (read by src/services/anticheat.py). Ladder and tournament games
with bots are noted separately - in their sessions (src/services/ladder.py).

What is checked:
* a request with the token of a player who has a game in progress - refusal (409);
* a request without a token from an address from which someone is currently playing - refusal: otherwise the ban
  could be bypassed by simply "not sending the token";
* a request with another account from the same address - allowed (different people can be on the same
  network), but counted against the player as an anti-cheat signal. By itself it does not penalise.

When Redis is unavailable the check lets the request through (fail-open), like the rate limit:
it is better to lose protection for a while than to refuse analysis to everyone.
"""

import logging

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import user_from_token
from src.api.rate_limit import client_ip
from src.core.errors import ApiError
from src.db import redis as redis_module
from src.db.session import get_db

logger = logging.getLogger(__name__)

# How long we remember which address a player connected from (refreshed on every connection).
PLAYER_IP_TTL_S = 12 * 60 * 60
# How long the counter of engine requests from the player's address is kept during their game: anti-cheat reads it right after
# the game, a day is a margin.
ENGINE_SIGNAL_TTL_S = 24 * 60 * 60



def _ip_players_key(ip: str) -> str:
    return f"fairplay:ip:{ip}"


def _engine_signal_key(game_id: int, user_id: int) -> str:
    return f"fairplay:engine_requests:{int(game_id)}:{int(user_id)}"


async def remember_player_ip(user_id: int, ip: str | None) -> None:
    """
    Remembers the address from which the player opened a game connection (called by src/api/websockets.py on every
    connection). A Redis failure is only written to the log: the connection is not broken because of it.
    """
    if not ip or ip == "unknown":
        return
    try:
        key = _ip_players_key(ip)
        await redis_module.redis_client.sadd(key, str(int(user_id)))
        await redis_module.redis_client.expire(key, PLAYER_IP_TTL_S)
    except Exception as exc:
        logger.warning("Could not remember address of user %s: %s", user_id, exc)


async def active_rated_game_id(user_id: int) -> int | None:
    """
    The id of the player's game in progress with a human. Casual games count too: the rating in them does not
    change, but a human sits on the other side, and engine hints against them are equally unfair.
    The function name speaks of a rated game, but any game in progress with a human is returned
    (state_manager.get_active_game_id, Redis key user:{id}:current_game).
    """
    from src.services.game_state import state_manager

    return await state_manager.get_active_game_id(user_id)


async def engine_requests_during_game(game_id: int, user_id: int) -> int:
    """How many times the engine was requested from the player's address during their game (an anti-cheat signal)."""
    try:
        return int(await redis_module.redis_client.get(_engine_signal_key(game_id, user_id)) or 0)
    except Exception as exc:
        logger.warning("Engine request signal unavailable for game %s: %s", game_id, exc)
        return 0


async def _record_engine_signal(game_id: int, user_id: int, requester: int) -> None:
    """
    An anti-cheat signal: during the game of player user_id another account (requester) requested the engine from their
    address.
    The request is still served; the counter is read by the game analysis after the game ends.
    """
    key = _engine_signal_key(game_id, user_id)
    if await redis_module.redis_client.incr(key) == 1:
        await redis_module.redis_client.expire(key, ENGINE_SIGNAL_TTL_S)
    logger.info(
        "Fair play signal: engine requested by user %s from the address of user %s during game %s",
        requester, user_id, game_id,
    )


async def optional_user_id(request: Request, db: AsyncSession) -> int | None:
    """
    The player id if the request came with a valid token, otherwise None - for endpoints open to guests too.
    A revoked or expired token does not cause a refusal: the request is simply treated as a guest one.
    """
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    user = await user_from_token(db, token)
    return user.id if user else None


async def forbid_engine_help_during_game(request: Request, db: AsyncSession = Depends(get_db)) -> None:
    """
    FastAPI dependency: 409 if the engine request coincides in time with a game with a human - one's own
    (engine_locked_in_game) or, for a request without a token, someone's from the same address (engine_locked_guest_ip).
    A request of another account from the address of the player in a game is let through, but recorded as an anti-cheat signal.
    Any failure of the check
    itself (Redis, database) does not block the request.
    """
    try:
        requester_id = await optional_user_id(request, db)

        if requester_id is not None and await active_rated_game_id(requester_id) is not None:
            raise ApiError(status.HTTP_409_CONFLICT, "engine_locked_in_game")

        ip = client_ip(request)
        if ip == "unknown":
            return
        for raw_uid in await redis_module.redis_client.smembers(_ip_players_key(ip)):
            player_id = int(raw_uid)
            if player_id == requester_id:
                continue
            game_id = await active_rated_game_id(player_id)
            if game_id is None:
                continue
            if requester_id is None:
                raise ApiError(status.HTTP_409_CONFLICT, "engine_locked_guest_ip")
            await _record_engine_signal(game_id, player_id, requester_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Fair play check unavailable, allowing the request: %s", exc)
