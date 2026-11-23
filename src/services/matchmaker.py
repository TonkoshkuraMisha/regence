# --- FILE: src/services/matchmaker.py ---
"""
Lobby, auto-matching, private invitations and the start of PvP games.

Invariants:
- a player cannot take part in two games at once: before the start the active game of both is checked,
  and the players themselves are reserved in Redis while the game is being created
  (SET NX), so that two tabs / two workers do not start two games in parallel;
- the rating is taken from the DB at the moment of matching, not from the user object cached by a
  long-lived WebSocket session;
- the rating range of a challenge is respected: auto-matching pairs only mutually suitable players,
  and with manual acceptance the accepting player's rating must fall within the challenge range.

Atomicity between workers is provided by Redis: a challenge or an invitation is "captured" by the one
whose DELETE of the key returned 1.

Where the data lives. Redis:
- ``queue:{base_ms}:{inc_ms}`` and ``queue:{base_ms}:{inc_ms}:casual`` -- challenge queues of one time control
  (ZSET: player -> rating at the moment of publication); rated and friendly ones are separate;
- ``queue:prefs:{user_id}`` -- the player's challenge parameters (HASH); a player has at most one challenge;
- ``active_queues`` -- names of the queues that ever had challenges (SET): the lobby list is built from it;
- ``matchmaking:reserve:{user_id}`` -- the player's reservation while a game starts (lives RESERVATION_TTL_MS);
- ``invite:{code}`` -- an invitation by link (JSON, lives INVITE_TTL_S).
PostgreSQL: the game record is created in ``games``; players' ratings are read from ``users`` by time control
category (src/services/rating.classify_time_control). The state of a running game in Redis is created by
src/services/game_state.py (``initialize_game``). Player actions come from src/api/websockets.py.
"""

import json
import logging
import random
import secrets
import string
import time
import uuid
from contextlib import asynccontextmanager

import chess
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.errors import DomainError
from src.db.session import AsyncSessionLocal
from src.models.game import Game, GameStatus
from src.models.user import RatingCategory, User
from src.services.game_engine import game_variant
from src.services.odds import pgn_header
from src.services.rating import classify_time_control

logger = logging.getLogger(__name__)

# The player's reservation while a game starts: released right after the start; the TTL is needed so that a crashed process
# does not
# block the player for longer than 15 seconds.
RESERVATION_TTL_MS = 15_000
INVITE_TTL_S = 900  # an invitation by link is valid for 15 minutes
UNBOUNDED_MAX_RATING = 10_000  # the upper bound of the "unlimited" range (above any rating)

# The allowed time control of a game between humans: from 15 seconds to 3 hours per game, increment up to 3 minutes per move.
MIN_BASE_TIME_MS = 15_000
MAX_BASE_TIME_MS = 3 * 60 * 60 * 1000
MAX_INCREMENT_MS = 180_000


# The invitation link code: length and alphabet (letters and digits, without characters resembling "-" and "_").
INVITE_CODE_LENGTH = 8
INVITE_CODE_ALPHABET = string.ascii_letters + string.digits


class MatchmakingError(DomainError):
    """An expected matchmaking refusal: a code from the registry src/core/errors.py and its parameters."""


def default_rating_window(rating: int) -> tuple[int, int]:
    """
    The default range if the client did not send its own: rating +- MATCHMAKING_DEFAULT_RATING_RANGE (setting
    src/core/config.py; 0, the default, means no limit).
    """
    spread = int(settings.MATCHMAKING_DEFAULT_RATING_RANGE)
    if spread <= 0:
        return 0, UNBOUNDED_MAX_RATING
    return max(0, rating - spread), rating + spread


def normalize_rating_window(min_rating, max_rating, rating: int) -> tuple[int, int]:
    """
    The opponent rating range for a challenge: the client's bounds, a missing one from the default range; negative
    values are raised to 0, swapped bounds are put in order.
    """
    default_min, default_max = default_rating_window(rating)
    lo = default_min if min_rating is None else max(0, int(min_rating))
    hi = default_max if max_rating is None else max(0, int(max_rating))
    return (lo, hi) if lo <= hi else (hi, lo)


def validate_time_control(base_time_ms, increment_ms) -> tuple[int, int]:
    """A time control in milliseconds; outside MIN_BASE_TIME_MS...MAX_INCREMENT_MS -- refusal invalid_time_control."""
    base_ms, inc_ms = int(base_time_ms), int(increment_ms)
    if not MIN_BASE_TIME_MS <= base_ms <= MAX_BASE_TIME_MS or not 0 <= inc_ms <= MAX_INCREMENT_MS:
        raise MatchmakingError("invalid_time_control")
    return base_ms, inc_ms


def _queue_name(base_ms, inc_ms, rated: bool) -> str:
    """Rated and friendly challenges lie in different queues and are never paired with each other."""
    return f"queue:{base_ms}:{inc_ms}" if rated else f"queue:{base_ms}:{inc_ms}:casual"


def _prefs_rated(prefs: dict) -> bool:
    """Whether a challenge is rated by its parameters from Redis; a challenge without the ``rated`` field counts as rated."""
    return str(prefs.get("rated", "1")) != "0"


def _ratings_compatible(rating_a: int, window_a: tuple[int, int], rating_b: int, window_b: tuple[int, int]) -> bool:
    """Mutual match: each player's rating falls within the other's range (bounds inclusive)."""
    return window_a[0] <= rating_b <= window_a[1] and window_b[0] <= rating_a <= window_b[1]



VARIANTS = ("standard", "chess960")  # game variants by invitation; an unknown value is replaced with standard


def chess960_start(number: int | None = None) -> str:
    """The starting position of a Fischer game (21.3) in Shredder-FEN: random of 960 or by number."""
    from src.services.game_engine import fen_of

    board = chess.Board.from_chess960_pos(random.randrange(960) if number is None else number)
    return fen_of(board)


def _odds_start(invite: dict, creator_id: int, white_id: int) -> dict | None:
    """
    The starting position and time of a game with odds or a Fischer game from an invitation -- when colours are already
    assigned.
    A 960 game has no odds and no rating; the placement is chosen by the server at the moment of the start (one for both
    players).
    "Hourglass" -- ordinary position and time, the hourglass flag changes how the clock runs (src/services/game_state.py).
    """
    from src.services.odds import HOURGLASS, odds_fen, odds_times

    if invite.get("variant") == "chess960":
        base_ms = int(invite.get("base_time_ms", 180000))
        return {"start_fen": chess960_start(), "white_time_ms": base_ms, "black_time_ms": base_ms, "kind": "chess960"}
    kind = invite.get("odds_kind") or ""
    if not kind:
        return None
    creator_white = creator_id == white_id
    giver_white = creator_white if invite.get("odds_giver", "creator") == "creator" else not creator_white
    giver = chess.WHITE if giver_white else chess.BLACK
    white_ms, black_ms = odds_times(kind, giver, int(invite.get("base_time_ms", 180000)))
    return {"start_fen": odds_fen(kind, giver), "white_time_ms": white_ms, "black_time_ms": black_ms, "kind": kind,
            "hourglass": kind == HOURGLASS}


class Matchmaker:
    """Manager of open challenges, automatic pairing and private links."""

    @property
    def redis(self):
        from src.db.redis import redis_client
        return redis_client

    @property
    def _state_manager(self):
        from src.services.game_state import state_manager
        return state_manager

    # ------------------------------------------------------------------ helpers

    @asynccontextmanager
    async def _session(self, db: AsyncSession | None):
        """The calling code's session, and if none was passed -- its own short one, closed on exit."""
        if db is not None:
            yield db
        else:
            async with AsyncSessionLocal() as session:
                yield session

    async def _fresh_user(self, session: AsyncSession, user_id: int) -> User | None:
        """Re-reads the user from the DB bypassing the identity map (the rating may have changed)."""
        return await session.get(User, int(user_id), populate_existing=True)

    async def _fresh_rating(self, session: AsyncSession, user_id: int, category: RatingCategory) -> int | None:
        user = await self._fresh_user(session, user_id)
        return user.rating_for(category) if user else None

    async def _ensure_not_in_game(self, user_id: int, *, is_self: bool) -> None:
        """
        Refusal if the player has a running game (key user:{id}:current_game, game_state.py): self_in_game -- when
        it is the requester himself, opponent_in_game -- when it is his opponent.
        """
        if await self._state_manager.get_active_game_id(user_id) is not None:
            if is_self:
                raise MatchmakingError("self_in_game")
            raise MatchmakingError("opponent_in_game")

    async def _reserve_players(self, *user_ids: int) -> str:
        """
        Reserves the players while a game starts (SET NX with a common token); if someone is busy -- rolls back the already
        taken reservations and refuses with players_busy. Returns the token for ``_release_players``.
        """
        token = uuid.uuid4().hex
        reserved: list[int] = []
        for uid in sorted({int(u) for u in user_ids}):
            ok = await self.redis.set(f"matchmaking:reserve:{uid}", token, nx=True, px=RESERVATION_TTL_MS)
            if not ok:
                await self._release_players(token, *reserved)
                raise MatchmakingError("players_busy")
            reserved.append(uid)
        return token

    async def _release_players(self, token: str, *user_ids: int) -> None:
        """
        Releases the reservation, but only one's own (by token): an expired reservation already taken by another start is not
        touched.
        """
        for uid in {int(u) for u in user_ids}:
            key = f"matchmaking:reserve:{uid}"
            if await self.redis.get(key) == token:
                await self.redis.delete(key)

    # ------------------------------------------------------------------ lobby

    async def join_queue(
            self,
            user_id: int,
            username: str,
            rating: int,
            base_time_ms: int,
            increment_ms: int,
            min_rating: int | None = None,
            max_rating: int | None = None,
            db: AsyncSession | None = None,
            rated: bool = True,
    ):
        """
        Immediately pairs with a suitable challenge from the lobby (the nearest by rating, with mutually
        suitable ranges) or publishes its own challenge. Returns game_id or None.
        rating must be fresh (the calling code re-reads the user from the DB).

        Candidates are taken only from the queue of the same time control and the same type (rated / friendly).
        A candidate's rating is the one with which they published the challenge. Publishing a new challenge removes the
        player's previous
        challenge: a player has at most one challenge in the lobby.
        """
        uid = int(user_id)
        rating = int(rating)
        base_ms, inc_ms = validate_time_control(base_time_ms, increment_ms)
        window = normalize_rating_window(min_rating, max_rating, rating)
        queue_name = _queue_name(base_ms, inc_ms, rated)

        await self._ensure_not_in_game(uid, is_self=True)

        candidates: list[tuple[int, int]] = []
        for cand_raw in await self.redis.zrange(queue_name, 0, -1):
            cand_id = int(cand_raw)
            if cand_id == uid:
                continue
            prefs = await self.redis.hgetall(f"queue:prefs:{cand_id}")
            if not prefs:
                continue
            cand_rating = int(prefs.get("rating", 0))
            cand_window = (int(prefs.get("min_rating", 0)), int(prefs.get("max_rating", UNBOUNDED_MAX_RATING)))
            if _ratings_compatible(rating, window, cand_rating, cand_window):
                candidates.append((abs(cand_rating - rating), cand_id))

        from src.services.connection_manager import manager
        for _, cand_id in sorted(candidates):
            try:
                matched_game_id = await self.accept_challenge(cand_id, uid, manager, self._state_manager, db=db)
            except MatchmakingError as err:
                if err.code == "self_in_game":
                    raise
                continue  # the challenge was taken in the meantime, the opponent is busy and so on -- try the next one
            if matched_game_id is not None:
                return matched_game_id

        await self.leave_queue(uid)
        await self.redis.sadd("active_queues", queue_name)
        await self.redis.zadd(queue_name, {str(uid): rating})
        await self.redis.hset(f"queue:prefs:{uid}", mapping={
            "user_id": str(uid),
            "username": str(username),
            "rating": str(rating),
            "min_rating": str(window[0]),
            "max_rating": str(window[1]),
            "base_time_ms": str(base_ms),
            "increment_ms": str(inc_ms),
            "rated": "1" if rated else "0",
        })
        logger.info(
            "User %s (%s) published %s challenge in lobby (%s+%s)",
            uid, username, "rated" if rated else "casual", base_ms, inc_ms,
        )
        return None

    async def leave_queue(self, user_id: int):
        """
        Removes a player's challenge from the lobby: from the queue of their time control, from the challenge settings and --
        in case of
        inconsistency -- from all active queues.
        """
        uid = int(user_id)
        prefs = await self.redis.hgetall(f"queue:prefs:{uid}")
        if prefs:
            queue_name = _queue_name(
                prefs.get("base_time_ms", 180000), prefs.get("increment_ms", 0), _prefs_rated(prefs),
            )
            await self.redis.zrem(queue_name, str(uid))
            await self.redis.delete(f"queue:prefs:{uid}")

        active_queues = await self.redis.smembers("active_queues")
        for qn in active_queues:
            await self.redis.zrem(qn, str(uid))

    async def get_queue_players(self) -> list[dict]:
        """
        Returns the list of all active challenges in the lobby (one per player): walks the queues from ``active_queues``
        and reads the challenge parameters from ``queue:prefs:{user_id}``; a queue entry without parameters is skipped.
        """
        players = []
        seen: set[int] = set()
        active_queues = await self.redis.smembers("active_queues")
        for queue_name in active_queues:
            user_ids = await self.redis.zrange(queue_name, 0, -1)
            for u_id in user_ids:
                uid = int(u_id)
                if uid in seen:
                    continue
                prefs = await self.redis.hgetall(f"queue:prefs:{uid}")
                if prefs:
                    seen.add(uid)
                    players.append({
                        "user_id": int(prefs.get("user_id", uid)),
                        "username": prefs.get("username", ""),
                        "rating": int(prefs.get("rating", 1200)),
                        "min_rating": int(prefs.get("min_rating", 0)),
                        "max_rating": int(prefs.get("max_rating", UNBOUNDED_MAX_RATING)),
                        "base_time_ms": int(prefs.get("base_time_ms", 180000)),
                        "increment_ms": int(prefs.get("increment_ms", 0)),
                        "rated": _prefs_rated(prefs),
                    })
        return players

    # ------------------------------------------------------------------ game start

    async def _create_game_record(
            self,
            session: AsyncSession,
            white_id: int,
            black_id: int,
            base_time: int,
            inc_time: int,
            now_ms: int,
            is_rated: bool = True,
            odds: dict | None = None,
    ) -> dict | None:
        """
        Creates the game record in ``games`` (status IN_PROGRESS) and returns the data for the Redis state and the
        match_found event; None -- one of the players is not in the DB. Ratings at the start of the game
        (``white_initial_rating``,
        ``black_initial_rating``) are taken fresh from ``users`` by time control category. The category is computed
        from the game's base_time and inc_time, not from the time reduced by odds. odds (``_odds_start``) sets the starting
        position, the sides' starting time and the "hourglass" clock (the hourglass flag).
        """
        white_user = await self._fresh_user(session, white_id)
        black_user = await self._fresh_user(session, black_id)
        if not white_user or not black_user:
            return None
        odds = odds or {}
        start_fen = odds.get("start_fen")
        white_ms, black_ms = odds.get("white_time_ms", base_time), odds.get("black_time_ms", base_time)

        category = classify_time_control(base_time, inc_time)
        white_rating = white_user.rating_for(category)
        black_rating = black_user.rating_for(category)

        new_game = Game(
            white_player_id=white_user.id,
            black_player_id=black_user.id,
            base_time_ms=base_time,
            increment_ms=inc_time,
            status=GameStatus.IN_PROGRESS,
            is_rated=is_rated,
            state_version=0,
            turn="w",
            board_fen=start_fen or chess.STARTING_FEN,
            initial_fen=start_fen,
            hourglass=bool(odds.get("hourglass")),
            white_time_ms=white_ms,
            black_time_ms=black_ms,
            last_move_at=now_ms,
            white_initial_rating=white_rating,
            black_initial_rating=black_rating,
        )
        session.add(new_game)
        await session.commit()
        await session.refresh(new_game)

        return {
            "game_id": new_game.id,
            "white_id": white_user.id,
            "black_id": black_user.id,
            "white_username": white_user.username,
            "white_rating": white_rating,
            "black_username": black_user.username,
            "black_rating": black_rating,
            "is_rated": is_rated,
            "start_fen": start_fen,
            "white_time_ms": white_ms,
            "black_time_ms": black_ms,
            "hourglass": bool(odds.get("hourglass")),
        }

    async def _create_match_record(
            self,
            session: AsyncSession,
            c_id: int,
            a_id: int,
            base_time: int,
            inc_time: int,
            now_ms: int,
            is_rated: bool = True,
    ) -> dict | None:
        """A lobby game: colours are random."""
        white_id, black_id = (c_id, a_id) if random.random() > 0.5 else (a_id, c_id)
        return await self._create_game_record(session, white_id, black_id, base_time, inc_time, now_ms, is_rated)

    async def _notify_match_found(self, connection_manager, created: dict, base_time: int, inc_time: int,
                                  arena: dict | None = None) -> None:
        """
        The match_found event to both players: identical game data plus their own colour and the opponent's number. Without
        connection_manager (the parameter is optional, tests call it that way) nothing is sent.
        """
        if connection_manager is None:
            return
        match_payload = {
            "event": "match_found",
            "game_id": created["game_id"],
            "white_username": created["white_username"],
            "white_rating": created["white_rating"],
            "black_username": created["black_username"],
            "black_rating": created["black_rating"],
            "is_rated": created.get("is_rated", True),
            "base_time_ms": base_time,
            "increment_ms": inc_time,
            "white_time_ms": created.get("white_time_ms", base_time),
            "black_time_ms": created.get("black_time_ms", base_time),
            "fen": created.get("start_fen") or chess.STARTING_FEN,
            "pgn": pgn_header(created["start_fen"]) if created.get("start_fen") else "",
            # A Fischer game (21.3) runs on a separate client page: the client goes there by this field.
            "variant": game_variant(created.get("start_fen")),
            # "Hourglass" (21.1): by this field the client runs the clock the same way as the server.
            "hourglass": bool(created.get("hourglass")),
            "state_version": 0,
        }
        if arena:
            # An arena game (33.3): by these fields the client shows "berserk" before the first move.
            match_payload["arena_id"] = arena["arena_id"]
            match_payload["berserk_allowed"] = bool(arena.get("berserk_allowed"))
        await connection_manager.send_personal_message(
            {**match_payload, "color": "white", "opponent_id": created["black_id"]}, created["white_id"],
        )
        await connection_manager.send_personal_message(
            {**match_payload, "color": "black", "opponent_id": created["white_id"]}, created["black_id"],
        )

    async def _start_reserved_game(
            self,
            session: AsyncSession,
            create,
            base_time: int,
            inc_time: int,
            connection_manager,
            players: tuple[int, int],
            arena: dict | None = None,
    ) -> dict | None:
        """The common part of the start: remove both from the queue, create the record, the Redis state, notify."""
        from src.services.connection_manager import manager as ws_manager
        for uid in players:
            await self.leave_queue(uid)
            # The player might have been watching someone else's game: otherwise its moves would keep arriving
            # during their own game.
            await ws_manager.remove_user_from_all_spectating(uid)

        created = await create(session, int(time.time() * 1000))
        if not created:
            return None

        await self._state_manager.initialize_game(
            game_id=created["game_id"],
            white_id=created["white_id"],
            black_id=created["black_id"],
            base_time_ms=base_time,
            increment_ms=inc_time,
            is_rated=created.get("is_rated", True),
            start_fen=created.get("start_fen"),
            white_time_ms=created.get("white_time_ms"),
            black_time_ms=created.get("black_time_ms"),
            arena=arena,
            hourglass=bool(created.get("hourglass")),
        )
        await self._notify_match_found(connection_manager, created, base_time, inc_time, arena)
        logger.info(
            "Match started: White(%s) vs Black(%s) in game %s",
            created["white_id"], created["black_id"], created["game_id"],
        )
        return {**created, "base_time_ms": base_time, "increment_ms": inc_time,
                "fen": created.get("start_fen") or chess.STARTING_FEN}

    async def start_pvp_game(
            self,
            white_id: int,
            black_id: int,
            base_time_ms: int,
            increment_ms: int,
            connection_manager=None,
            db: AsyncSession | None = None,
            initiator_id: int | None = None,
            is_rated: bool = True,
            odds: dict | None = None,
            arena: dict | None = None,
    ) -> dict:
        """
        Starts a game with given colours (invitation, rematch, arena pairing). odds -- the starting position and time
        of a game with odds or a Fischer game (``_odds_start``); such a game is always unrated, whatever
        is passed in is_rated. arena -- the arena game marker (``arena._game_marker``): the arena number and whether
        berserk is available. initiator_id -- who initiated the start: the refusal code depends on it if someone is already
        playing (self_in_game -- about the initiator himself, opponent_in_game -- about his opponent; without initiator_id
        both players
        count as initiators). Both players are reserved for the start; the reservation is released in any case.
        """
        white_id, black_id = int(white_id), int(black_id)
        if white_id == black_id:
            raise MatchmakingError("self_play")
        base_ms, inc_ms = validate_time_control(base_time_ms, increment_ms)

        token = await self._reserve_players(white_id, black_id)
        try:
            for uid in (white_id, black_id):
                is_self = initiator_id is None or uid == int(initiator_id)
                await self._ensure_not_in_game(uid, is_self=is_self)

            async with self._session(db) as session:
                started = await self._start_reserved_game(
                    session,
                    lambda s, now_ms: self._create_game_record(
                        s, white_id, black_id, base_ms, inc_ms, now_ms, is_rated and not odds, odds=odds,
                    ),
                    base_ms, inc_ms, connection_manager, (white_id, black_id), arena=arena,
                )
            if not started:
                raise MatchmakingError("player_not_found")
            return started
        finally:
            await self._release_players(token, white_id, black_id)

    async def accept_challenge(
            self,
            challenger_id: int,
            acceptor_id: int,
            connection_manager,
            state_manager=None,
            db: AsyncSession | None = None,
    ):
        """
        Atomic acceptance of a challenge from the lobby: busy and rating range checks, capture of the
        challenge, creating the game and notifying both players. Returns game_id or raises
        MatchmakingError.

        The challenge range is checked against the accepting player's fresh rating from the DB -- in the challenge's time
        control category.
        A challenge of a player who is already playing another game is considered stale and removed from the lobby. Colours
        are random.
        """
        c_id = int(challenger_id)
        a_id = int(acceptor_id)
        if c_id == a_id:
            raise MatchmakingError("own_challenge")

        token = await self._reserve_players(c_id, a_id)
        try:
            await self._ensure_not_in_game(a_id, is_self=True)

            prefs_key = f"queue:prefs:{c_id}"
            prefs = await self.redis.hgetall(prefs_key)
            if not prefs:
                raise MatchmakingError("challenge_gone")

            if await self._state_manager.get_active_game_id(c_id) is not None:
                await self.leave_queue(c_id)  # the challenger is already playing, the challenge is stale
                raise MatchmakingError("opponent_in_game")

            base_time = int(prefs.get("base_time_ms", 180000))
            inc_time = int(prefs.get("increment_ms", 0))
            is_rated = _prefs_rated(prefs)
            category = classify_time_control(base_time, inc_time)

            async with self._session(db) as session:
                acceptor_rating = await self._fresh_rating(session, a_id, category)
                if acceptor_rating is None:
                    raise MatchmakingError("player_not_found")
                lo = int(prefs.get("min_rating", 0))
                hi = int(prefs.get("max_rating", UNBOUNDED_MAX_RATING))
                if not lo <= acceptor_rating <= hi:
                    raise MatchmakingError("rating_out_of_range", rating=acceptor_rating, min=lo, max=hi)

                # Capturing the challenge: only one of the competing accepters can delete the key.
                if not await self.redis.delete(prefs_key):
                    raise MatchmakingError("challenge_gone")

                started = await self._start_reserved_game(
                    session,
                    lambda s, now_ms: self._create_match_record(
                        s, c_id, a_id, base_time, inc_time, now_ms, is_rated,
                    ),
                    base_time, inc_time, connection_manager, (c_id, a_id),
                )
            if not started:
                raise MatchmakingError("player_not_found")
            return started["game_id"]
        finally:
            await self._release_players(token, c_id, a_id)

    # ------------------------------------------------------------------ invitations

    async def create_private_invite(
            self,
            user_id: int,
            username: str = "",
            rating: int = 1200,
            base_time_ms: int = 180000,
            increment_ms: int = 2000,
            color_pref: str = "random",
            rated: bool = True,
            odds_kind: str = "",
            odds_giver: str = "creator",
            variant: str = "standard",
    ) -> dict:
        """
        An invitation by link: a code with the game parameters (time control, colour, type, odds, variant) is stored in Redis
        (``invite:{code}``) until accepted or until INVITE_TTL_S expires. Unknown colour, odds and variant values
        are replaced with defaults rather than rejected. The code is up to 8 letters and digits. The player's previous
        invitations
        are not revoked by this method: each lives until its own expiry.
        """
        from src.services.odds import GIVERS, KINDS

        await self._ensure_not_in_game(user_id, is_self=True)
        base_ms, inc_ms = validate_time_control(base_time_ms, increment_ms)
        if odds_kind not in KINDS:
            odds_kind = ""
        if odds_giver not in GIVERS:
            odds_giver = "creator"
        if variant not in VARIANTS:
            variant = "standard"
        if variant == "chess960":
            odds_kind = ""  # odds and 960 never occur together

        # Exactly INVITE_CODE_LENGTH letters and digits: the former token_urlsafe with "-" and "_" cut out sometimes gave a
        # code shorter than six.
        code = "".join(secrets.choice(INVITE_CODE_ALPHABET) for _ in range(INVITE_CODE_LENGTH))
        if color_pref not in ("white", "black", "random"):
            color_pref = "random"

        payload = {
            "code": code,
            "creator_id": int(user_id),
            "creator_username": username,
            "creator_rating": int(rating),
            "base_time_ms": base_ms,
            "increment_ms": inc_ms,
            "color_pref": color_pref,
            # A game with odds or a Fischer game does not change the rating (as with a bot).
            "rated": bool(rated) and not odds_kind and variant == "standard",
            "odds_kind": odds_kind,
            "odds_giver": odds_giver,
            "variant": variant,
        }
        await self.redis.set(f"invite:{code}", json.dumps(payload), ex=INVITE_TTL_S)
        return payload

    async def get_private_invite(self, code: str) -> dict | None:
        """The invitation parameters by code without consuming it; None -- no such code or it has expired."""
        raw = await self.redis.get(f"invite:{code}")
        if not raw:
            return None
        return json.loads(raw)

    async def accept_private_invite(self, code: str, acceptor_id: int) -> dict | None:
        """
        Atomically consumes the invitation and assigns colours (without starting the game). None -- no invitation, it has
        expired,
        the author accepts it himself or someone else managed to accept it. The author's colour is by their choice, "random"
        -- a draw. In the response
        ``_raw`` is the original record, to return the invitation to Redis if the game start fails.
        """
        key = f"invite:{code}"

        raw = await self.redis.get(key)
        if not raw:
            return None

        invite = json.loads(raw)
        creator_id = int(invite["creator_id"])
        if creator_id == int(acceptor_id):
            return None

        if not await self.redis.delete(key):
            return None  # the invitation has already been accepted by someone else

        color_pref = invite.get("color_pref", "random")
        if color_pref == "white":
            white_id, black_id = creator_id, int(acceptor_id)
        elif color_pref == "black":
            white_id, black_id = int(acceptor_id), creator_id
        else:
            if random.random() < 0.5:
                white_id, black_id = creator_id, int(acceptor_id)
            else:
                white_id, black_id = int(acceptor_id), creator_id

        return {
            "code": code,
            "creator_id": creator_id,
            "acceptor_id": int(acceptor_id),
            "white_id": white_id,
            "black_id": black_id,
            "base_time_ms": int(invite.get("base_time_ms", 180000)),
            "increment_ms": int(invite.get("increment_ms", 0)),
            "rated": bool(invite.get("rated", True)),
            "odds": _odds_start(invite, creator_id, white_id),
            "_raw": raw,
        }

    async def start_game_from_invite(
            self,
            code: str,
            acceptor_id: int,
            connection_manager=None,
            db: AsyncSession | None = None,
    ) -> dict:
        """
        Accepts the invitation and starts the game. If the start failed (for example, one of the players is already
        in a game or busy with another start), the invitation is returned to Redis so that it can be
        used later -- with a new full INVITE_TTL_S lifetime.
        """
        await self._ensure_not_in_game(acceptor_id, is_self=True)

        accepted = await self.accept_private_invite(code, acceptor_id)
        if not accepted:
            raise MatchmakingError("invite_invalid")

        try:
            return await self.start_pvp_game(
                accepted["white_id"], accepted["black_id"],
                accepted["base_time_ms"], accepted["increment_ms"],
                connection_manager=connection_manager, db=db, initiator_id=acceptor_id,
                is_rated=accepted["rated"], odds=accepted["odds"],
            )
        except MatchmakingError:
            await self.redis.set(f"invite:{code}", accepted["_raw"], ex=INVITE_TTL_S)
            raise


matchmaker = Matchmaker()
