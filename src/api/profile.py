# --- FILE: src/api/profile.py ---
"""
The player's profile and everything that pages read about games over HTTP (/profile).

* /me and /me/settings - one's own profile: ratings, the provisional rating flag, language, theme, avatar, country.
* /leaderboard - the leaderboard by time-control category: without bots and archived players, without deleted
  accounts and players with the unfair-play flag.
* /{username}, /stats, /rating-history, /games, /achievements - the public profile. The rating history is taken from
  the values saved when each game finished (games.*_initial_rating and *_rating_delta), and is not
  recomputed.
* /games/my-active - a snapshot of the game in progress (position, clocks, colour, berserk): the client takes it on page load
  and by polling - in case the WebSocket event did not arrive. /games/{id}/summary - the game result for a client that
  missed game_over. /games/live - games in progress right now (for spectators).
* /matchmaking/* - the same lobby actions as over WebSocket (challenge, cancel, accept), in case the socket drops;
  protected from a race with the WebSocket message - the game is created by src/services/matchmaker.py. /matchmaking/queue -
  the list of open challenges.
* /games/{id}/pgn - the game record as a file. /games/{id}/blindfold - the "blindfold" mark on one's own casual game.

Login is required for /me, /me/settings, /games/my-active, /matchmaking/join, /leave and /accept and /games/{id}/blindfold;
the rest is open to everyone. Where the data comes from: profiles and archive - tables users and games, games in progress and
the lobby - Redis.

Archived champion pages load their games on first access (src/db/seed.ensure_champion_seeded).
"""

import time
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, asc, case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.api.bots import CUSTOM_BOT_USERNAME
from src.api.deps import get_current_user
from src.core.errors import ApiError
from src.db.seed import ensure_champion_seeded, extract_pgn_metadata, get_champion_meta
from src.db.session import get_db
from src.models.game import Game, GameStatus
from src.models.user import RATING_CATEGORIES, RatingCategory, User
from src.schemas.user import username_key
from src.services import account_state, arena_awards
from src.services.conferences import conference_of
from src.services.ladder import current_rung as ladder_current_rung
from src.services.ladder import rungs as ladder_rungs
from src.services.rating import (
    ESTIMATED_MOVES,
    PROVISIONAL_GAMES,
    category_duration_bounds_ms,
    classify_time_control,
)

router = APIRouter(prefix="/profile", tags=["Profile & Games"])


class QueueJoinRequest(BaseModel):
    """A lobby challenge over HTTP: time control, the opponent rating bounds and the game type (rated by default)."""
    base_time_ms: int = 180000
    increment_ms: int = 0
    min_rating: int | None = None
    max_rating: int | None = None
    rated: bool = True


async def _resolve_user(db: AsyncSession, username: str) -> User | None:
    """The player by the name from the address; a deleted or closed account (tasks 17.5, 23.1) has no public profile or
    games."""
    user = await _find_user(db, username)
    return None if account_state.is_closed(user) else user


async def _find_user(db: AsyncSession, username: str) -> User | None:
    """
    The users record by the name from the address. Order: a champion of the archive (their games are loaded from PGN on first
    access -
    src/db/seed.py) -> the exact name -> the name case-insensitively among accounts (username_key) -> case-insensitively
    among archived players and bots. Deleted accounts are cut off by _resolve_user.
    """
    champ_meta = get_champion_meta(username)
    if champ_meta is not None:
        champ_user = await ensure_champion_seeded(db, champ_meta["id"])
        if champ_user is not None:
            return champ_user

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    if user:
        return user

    # Case-insensitively (/profile/Alice for alice) - only an exact name match. A substring
    # search (ILIKE '%name%') would open, for a non-existent or mistyped name, the profile and
    # games of a stranger, and "%" and "_" in the address matched anyone.
    result = await db.execute(select(User).where(User.username_key == username_key(username)))
    user = result.scalars().first()
    if user:
        return user

    # Archived players and bots without username_key.
    result = await db.execute(
        select(User).where(func.lower(User.username) == username.lower()).order_by(User.id).limit(1)
    )
    return result.scalars().first()


async def _build_active_game_payload(db: AsyncSession, game_id: int, user_id: int) -> dict | None:
    """
    Builds a full snapshot of the active game for the player (colour, clocks, FEN, PGN, state version) from the game state in
    Redis; None - the game is not in progress or the player does not take part in it. The clock of the side that is thinking is
    reduced by the time
    that has passed since the last move. Built as the WebSocket match_found event (the event field is set), but without the
    fields
    variant and arena_id, which are in the snapshot at WebSocket connection
    (src/api/websockets._send_active_game_snapshot_if_exists).
    """
    from src.services.game_state import berserk_fields, is_rated_state, pending_draw_offer, state_manager

    state = await state_manager.get_game_state(game_id)
    if not state or state.get("status") != "in_progress":
        return None

    white_id = int(state["white_id"])
    black_id = int(state["black_id"])
    if int(user_id) not in (white_id, black_id):
        return None

    white_user = await db.get(User, white_id)
    black_user = await db.get(User, black_id)
    category = classify_time_control(int(state.get("base_time_ms", 180000)), int(state.get("increment_ms", 0)))

    now_ms = int(time.time() * 1000)
    elapsed = max(0, now_ms - int(state.get("last_move_at", now_ms)))
    turn = state.get("turn", "white")
    w_ms = int(state.get("white_time_ms", 180000))
    b_ms = int(state.get("black_time_ms", 180000))

    white_time = max(0, w_ms - elapsed) if turn in ("white", "w") else w_ms
    black_time = max(0, b_ms - elapsed) if turn in ("black", "b") else b_ms

    return {
        "active": True,
        "event": "match_found",
        "game_id": int(game_id),
        "color": "white" if int(user_id) == white_id else "black",
        "opponent_id": black_id if int(user_id) == white_id else white_id,
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
        "state_version": int(state.get("state_version", 0)),
        "draw_offer_from": pending_draw_offer(state),
        # An arena game (33.3): the berserk button and marks for a client that took the game by polling rather than from
        # WebSocket.
        **berserk_fields(state),
    }


@router.get("/me")
async def get_my_profile(current_user: User = Depends(get_current_user)):
    """
    One's own profile: ratings, the unfair-play flag (the numeric trust factor is not given out), e-mail, categories with a
    provisional
    rating, language, theme, avatar, country and conference.
    """
    return {
        "id": current_user.id,
        "username": current_user.username,
        "bullet_rating": current_user.bullet_rating,
        "blitz_rating": current_user.blitz_rating,
        "rapid_rating": current_user.rapid_rating,
        "classical_rating": current_user.classical_rating,
        # The player sees their own flag; the numeric trust factor is not given out, so that it cannot be
        # used to calibrate bypassing anti-cheat.
        "is_cheater": current_user.is_cheater,
        "created_at": current_user.created_at,
        # The confirmed e-mail (task 17.5) - only to the player themselves.
        "email": current_user.email,
        # Provisional rating (task 17.8): categories where fewer than PROVISIONAL_GAMES games were played (K = 40).
        "provisional": [c for c in RATING_CATEGORIES if current_user.games_played_for(c) < PROVISIONAL_GAMES],
        # Languages (task 17.7): the interface language from the profile and the "translation helper" mode.
        "language": current_user.language,
        "translation_helper": current_user.translation_helper,
        # Appearance (task 18.3): the theme set.
        "theme_preset": current_user.theme_preset,
        "avatar": current_user.avatar,
        # Conference (task 33.6): the country from the profile and its conference; chosen via PUT /conferences/me.
        "country": current_user.country,
        "conference": conference_of(current_user.country),
        # Kid mode (task 23.1, src/services/kid_mode.py) and whether turning it off needs the guardian code.
        "kid_mode": current_user.kid_mode,
        "kid_guardian_code": current_user.kid_guardian_hash is not None,
    }


class SettingsIn(BaseModel):
    language: Literal["en", "uk"] | None = None
    translation_helper: bool | None = None
    theme_preset: str | None = Field(None, min_length=1, max_length=32, pattern=r"^[a-z0-9_]+$")
    avatar: str | None = Field(None, pattern=r"^[wb][KQRBNP]-[0-7]$")


@router.patch("/me/settings")
async def update_my_settings(payload: SettingsIn, db: AsyncSession = Depends(get_db),
                             current_user: User = Depends(get_current_user)):
    """
    Settings of one's own profile: the interface language and the "translation helper" mode (task 17.7), the theme set (18.3)
    and
    the avatar (18.4). Only the sent fields are changed; the response has all four values. The country is changed separately -
    PUT /conferences/me.
    """
    if payload.language is not None:
        current_user.language = payload.language
    if payload.translation_helper is not None:
        current_user.translation_helper = payload.translation_helper
    if payload.theme_preset is not None:
        current_user.theme_preset = payload.theme_preset
    if payload.avatar is not None:
        current_user.avatar = payload.avatar
    await db.commit()
    return {"language": current_user.language, "translation_helper": current_user.translation_helper,
            "theme_preset": current_user.theme_preset, "avatar": current_user.avatar}


_LEADERBOARD_RATING_COLUMN: dict[RatingCategory, Any] = {
    "bullet": User.bullet_rating,
    "blitz": User.blitz_rating,
    "rapid": User.rapid_rating,
    "classical": User.classical_rating,
}


@router.get("/leaderboard")
async def get_leaderboard(
        category: RatingCategory = Query("blitz", description="Time-control category"),
        limit: int = Query(50, ge=1, le=100, description="Number of players in the top"),
        db: AsyncSession = Depends(get_db),
):
    """
    The leaderboard of a category: without bots and archived players, without deleted accounts and players with the unfair-play
    flag. Open to everyone. The order is by the current rating of the category (users.<category>_rating); players with a
    provisional
    rating and those who have not yet played in the category are not excluded from the table.
    """
    rating_column = _LEADERBOARD_RATING_COLUMN[category]
    query = (
        select(User)
        .where(User.is_cheater == False, User.is_bot == False, *account_state.open_account())  # noqa: E712
        .order_by(desc(rating_column))
        .limit(limit)
    )
    result = await db.execute(query)
    top_users = result.scalars().all()

    return [
        {"rank": index + 1, "username": user.username, "avatar": user.avatar, "rating": user.rating_for(category)}
        for index, user in enumerate(top_users)
    ]


@router.get("/games/my-active")
async def get_my_active_game(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    """
    Returns the current active game of the authorised player (to synchronise the start and moves): the game id is from
    the Redis key user:{id}:current_game, the state is from there too. No game - {"active": false}.
    """
    from src.services.game_state import state_manager

    gid_str = await state_manager.redis.get(f"user:{current_user.id}:current_game")
    if not gid_str:
        return {"active": False}

    payload = await _build_active_game_payload(db, int(gid_str), current_user.id)
    if not payload:
        return {"active": False}
    return payload


async def _active_game_payload_or_none(db: AsyncSession, user_id: int) -> dict | None:
    """A snapshot of the player's game in progress, if there is one - for a lobby request that lost the race with WebSocket."""
    from src.services.game_state import state_manager

    game_id = await state_manager.get_active_game_id(user_id)
    if game_id is None:
        return None
    return await _build_active_game_payload(db, game_id, user_id)


@router.post("/matchmaking/join")
async def join_matchmaking_http(
        req: QueueJoinRequest,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    """Publishes a challenge to the lobby over HTTP (or starts a match immediately if an opponent is already waiting)."""
    from src.services.matchmaker import MatchmakingError, matchmaker

    try:
        matched_gid = await matchmaker.join_queue(
            user_id=current_user.id,
            username=current_user.username,
            rating=current_user.rating_for(classify_time_control(req.base_time_ms, req.increment_ms)),
            base_time_ms=req.base_time_ms,
            increment_ms=req.increment_ms,
            min_rating=req.min_rating,
            max_rating=req.max_rating,
            db=db,
            rated=req.rated,
        )
    except MatchmakingError as err:
        # The frontend duplicates the action over WS and HTTP: if WS has already started the game, we return it.
        payload = await _active_game_payload_or_none(db, current_user.id) if err.code == "self_in_game" else None
        if payload:
            return payload
        raise err.to_http(409) from err
    if matched_gid is not None:
        payload = await _build_active_game_payload(db, int(matched_gid), current_user.id)
        if payload:
            return payload
    return {"active": False, "queued": True}


@router.post("/matchmaking/leave")
async def leave_matchmaking_http(current_user: User = Depends(get_current_user)):
    """Removes the player's challenge from the lobby queue."""
    from src.services.matchmaker import matchmaker
    await matchmaker.leave_queue(current_user.id)
    return {"status": "left"}


@router.post("/matchmaking/accept/{target_user_id}")
async def accept_challenge_http(
        target_user_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    """
    Accepts an opponent's challenge from the lobby over HTTP and returns the data of the game that has started.
    Safe against races with the WebSocket message accept_challenge.
    """
    from src.services.connection_manager import manager
    from src.services.game_state import state_manager
    from src.services.matchmaker import MatchmakingError, matchmaker

    if int(target_user_id) == current_user.id:
        raise ApiError(400, "own_challenge")

    try:
        game_id = await matchmaker.accept_challenge(
            challenger_id=int(target_user_id),
            acceptor_id=current_user.id,
            connection_manager=manager,
            state_manager=state_manager,
            db=db,
        )
    except MatchmakingError as err:
        # The frontend duplicates the action over WS and HTTP: the request that lost the race returns the
        # already started game of the player rather than an error.
        if err.code in ("self_in_game", "challenge_gone", "players_busy"):
            payload = await _active_game_payload_or_none(db, current_user.id)
            if payload:
                return payload
        status_code = 404 if err.code == "challenge_gone" else 409
        raise err.to_http(status_code) from err

    payload = await _build_active_game_payload(db, int(game_id), current_user.id)
    if not payload:
        raise ApiError(404, "game_init_failed")

    return payload


@router.get("/games/live")
async def get_live_games(db: AsyncSession = Depends(get_db)):
    """
    Returns the list of active games in progress right now (for the Live tab and spectator mode). Open to everyone.
    The source is the Redis set active_games and the state of each game; names and ratings - from users, the number of
    spectators - from connection_manager. New games first.
    """
    from src.services.connection_manager import manager
    from src.services.game_state import is_rated_state, state_manager

    game_ids = await state_manager.redis.smembers("active_games")
    if not game_ids:
        return []

    active_states: list[tuple[int, dict]] = []
    user_ids: set[int] = set()

    for gid_raw in game_ids:
        try:
            gid = int(gid_raw)
        except ValueError:
            continue
        state = await state_manager.get_game_state(gid)
        if not state or state.get("status") != "in_progress":
            continue

        white_id = int(state["white_id"])
        black_id = int(state["black_id"])
        user_ids.add(white_id)
        user_ids.add(black_id)
        active_states.append((gid, state))

    if not active_states:
        return []

    users_res = await db.execute(select(User).where(User.id.in_(user_ids)))
    users_map = {u.id: u for u in users_res.scalars().all()}

    live_list: list[dict[str, Any]] = []
    for gid, state in active_states:
        white_id = int(state["white_id"])
        black_id = int(state["black_id"])
        white_user = users_map.get(white_id)
        black_user = users_map.get(black_id)
        spectators_set = await manager.get_spectator_ids(gid)
        category = classify_time_control(int(state.get("base_time_ms", 180000)), int(state.get("increment_ms", 0)))

        live_list.append({
            "game_id": gid,
            "white_id": white_id,
            "black_id": black_id,
            "white_username": white_user.username if white_user else "",
            "white_rating": white_user.rating_for(category) if white_user else 1200,
            "black_username": black_user.username if black_user else "",
            "black_rating": black_user.rating_for(category) if black_user else 1200,
            "is_rated": is_rated_state(state),
            "base_time_ms": int(state.get("base_time_ms", 180000)),
            "increment_ms": int(state.get("increment_ms", 0)),
            "state_version": int(state.get("state_version", 0)),
            "spectators_count": len(spectators_set),
        })

    live_list.sort(key=lambda x: x["game_id"], reverse=True)
    return live_list


@router.get("/{username}/achievements")
async def get_user_achievements(username: str, db: AsyncSession = Depends(get_db)):
    """Achievements and the club title (task 17.6): progress for each, newly unlocked ones are recorded."""
    from src.services import achievements

    user = await _resolve_user(db, username)
    if not user:
        raise ApiError(404, "user_not_found", username=username)
    return await achievements.evaluate(db, user)


@router.get("/{username}")
async def get_user_profile(username: str, db: AsyncSession = Depends(get_db)):
    """The public profile of a player: ratings, avatar, ladder. There is nothing personal (e-mail, settings) in it."""
    user = await _resolve_user(db, username)
    if not user:
        raise ApiError(404, "user_not_found", username=username)

    return {
        "id": user.id,
        "username": user.username,
        "avatar": user.avatar,
        # Kid mode (task 23.1): the client hides "Message" and the feed; the server refuses them anyway.
        "kid_mode": user.kid_mode,
        "bullet_rating": user.bullet_rating,
        "blitz_rating": user.blitz_rating,
        "rapid_rating": user.rapid_rating,
        "classical_rating": user.classical_rating,
        "created_at": user.created_at,
        # The club ladder - separate from the rating of games between people (src/services/ladder.py).
        "ladder": {
            "rating": user.ladder_rating,
            "games": user.ladder_games,
            "step": (await ladder_current_rung(db, user))[0],
            "total": len(ladder_rungs()),
        },
        # Arena cups (task 33.5): first, second and third places (src/services/arena_awards.py).
        "arena_trophies": await arena_awards.trophies(db, user.id),
    }


def _archive_conditions(user_id: int) -> list:
    """The player's games that are shown in the history: finished and with a move record."""
    return [
        or_(Game.white_player_id == user_id, Game.black_player_id == user_id),
        Game.status == GameStatus.COMPLETED,
        Game.pgn.is_not(None),
        Game.pgn != "",
        Game.is_simulation.is_(False),  # bot games in tournaments are not in the archive and statistics
    ]


@router.get("/{username}/stats")
async def get_user_stats(username: str, db: AsyncSession = Depends(get_db)):
    """
    Totals over all of the player's games (the same ones as in the history): total, wins, draws, losses.
    Computed with one DB query - the profile page used to count them over the last 30 games.
    """
    user = await _resolve_user(db, username)
    if not user:
        raise ApiError(404, "user_not_found", username=username)

    is_white = Game.white_player_id == user.id
    won = or_(and_(is_white, Game.result == "1-0"), and_(~is_white, Game.result == "0-1"))
    lost = or_(and_(is_white, Game.result == "0-1"), and_(~is_white, Game.result == "1-0"))
    row = (await db.execute(
        select(
            func.count(Game.id),
            func.coalesce(func.sum(case((won, 1), else_=0)), 0),
            func.coalesce(func.sum(case((Game.result == "1/2-1/2", 1), else_=0)), 0),
            func.coalesce(func.sum(case((lost, 1), else_=0)), 0),
        ).where(*_archive_conditions(user.id))
    )).one()

    return {
        "total": int(row[0]),
        "wins": int(row[1]),
        "draws": int(row[2]),
        "losses": int(row[3]),
        # Rated games per category - the page uses them to choose which chart to show first.
        "rated_games": {category: user.games_played_for(category) for category in _LEADERBOARD_RATING_COLUMN},
    }


@router.get("/{username}/rating-history")
async def get_rating_history(
        username: str,
        category: RatingCategory = Query("blitz", description="Time-control category"),
        limit: int = Query(200, ge=1, le=1000, description="How many latest games to return"),
        db: AsyncSession = Depends(get_db),
):
    """
    The player's rating after each rated game of the category - in chronological order.
    Taken from the values saved when the game finished (rating before the game + change),
    rather than approximately reconstructed on the client.
    """
    user = await _resolve_user(db, username)
    if not user:
        raise ApiError(404, "user_not_found", username=username)

    estimated_ms = Game.base_time_ms + ESTIMATED_MOVES * Game.increment_ms
    lower, upper = category_duration_bounds_ms(category)
    conditions = [
        or_(Game.white_player_id == user.id, Game.black_player_id == user.id),
        Game.status == GameStatus.COMPLETED,
        Game.is_rated == True,  # noqa: E712
        Game.finished_at.is_not(None),
        Game.white_initial_rating.is_not(None),
        Game.black_initial_rating.is_not(None),
        Game.white_rating_delta.is_not(None),
        Game.black_rating_delta.is_not(None),
    ]
    if lower is not None:
        conditions.append(estimated_ms >= lower)
    if upper is not None:
        conditions.append(estimated_ms < upper)

    rows = (await db.execute(
        select(
            Game.id, Game.finished_at, Game.white_player_id, Game.result,
            Game.white_initial_rating, Game.white_rating_delta,
            Game.black_initial_rating, Game.black_rating_delta,
        )
        .where(*conditions)
        .order_by(desc(Game.finished_at), desc(Game.id))
        .limit(limit)
    )).all()

    points = []
    for game_id, finished_at, white_id, result, w_initial, w_delta, b_initial, b_delta in reversed(rows):
        played_white = white_id == user.id
        initial, delta = (w_initial, w_delta) if played_white else (b_initial, b_delta)
        points.append({
            "game_id": game_id,
            "finished_at": finished_at.isoformat(),
            "rating": initial + delta,
            "delta": delta,
            "color": "white" if played_white else "black",
            "result": result,
        })

    return {"category": category, "current_rating": user.rating_for(category), "points": points}


@router.get("/{username}/games")
async def get_user_games(
        username: str,
        limit: int = Query(25, ge=1, le=2000),
        offset: int = Query(0, ge=0),
        sort: str = Query("desc"),
        db: AsyncSession = Depends(get_db),
):
    """
    The player's game history, paginated: finished games with a move record - with humans, with bots and archived, with
    the opponents' names and the rating change.
    """
    user = await _resolve_user(db, username)
    if not user:
        raise ApiError(404, "user_not_found", username=username)

    WhiteUser = aliased(User)
    BlackUser = aliased(User)

    conditions = _archive_conditions(user.id)

    count_query = select(func.count(Game.id)).where(*conditions)
    total_count = (await db.execute(count_query)).scalar() or 0

    null_date_flag = case(
        (or_(Game.pgn_date.is_(None), Game.pgn_date == "", Game.pgn_date.like("?%")), 1),
        else_=0,
    )

    if sort == "asc":
        order_clauses = [
            asc(null_date_flag),
            asc(Game.pgn_date),
            asc(Game.finished_at),
            asc(Game.id),
        ]
    else:
        order_clauses = [
            asc(null_date_flag),
            desc(Game.pgn_date),
            desc(Game.finished_at),
            desc(Game.id),
        ]

    games_query = (
        select(
            Game.id,
            Game.status,
            Game.is_rated,
            Game.result,
            Game.pgn_date,
            Game.site,
            Game.eco,
            Game.finished_at,
            Game.pgn,
            Game.base_time_ms,
            Game.increment_ms,
            Game.personality_name,
            Game.assisted,
            Game.blindfold_level,
            Game.blindfold_peeks,
            WhiteUser.username,
            WhiteUser.bullet_rating,
            WhiteUser.blitz_rating,
            WhiteUser.rapid_rating,
            WhiteUser.classical_rating,
            BlackUser.username,
            BlackUser.bullet_rating,
            BlackUser.blitz_rating,
            BlackUser.rapid_rating,
            BlackUser.classical_rating,
        )
        .join(WhiteUser, Game.white_player_id == WhiteUser.id)
        .join(BlackUser, Game.black_player_id == BlackUser.id)
        .where(*conditions)
        .order_by(*order_clauses)
        .limit(limit)
        .offset(offset)
    )

    rows = (await db.execute(games_query)).all()

    items = []
    for (
            game_id,
            status_val,
            is_rated,
            result_val,
            pgn_date,
            site,
            eco,
            finished_at,
            pgn_text,
            base_time_ms,
            increment_ms,
            personality_name,
            assisted,
            blindfold_level,
            blindfold_peeks,
            w_name,
            w_bullet,
            w_blitz,
            w_rapid,
            w_classical,
            b_name,
            b_bullet,
            b_blitz,
            b_rapid,
            b_classical,
    ) in rows:
        # The opponent's current rating in the category of exactly this game (bullet/blitz/rapid/classical),
        # not a general one - there are no separate "general" ratings in the system any more.
        category = classify_time_control(base_time_ms, increment_ms)
        w_rating = {"bullet": w_bullet, "blitz": w_blitz, "rapid": w_rapid, "classical": w_classical}[category]
        b_rating = {"bullet": b_bullet, "blitz": b_blitz, "rapid": b_rapid, "classical": b_classical}[category]
        if (not pgn_date or not site or not eco or not result_val or result_val == "*") and pgn_text:
            fallback_meta = extract_pgn_metadata(pgn_text, fallback_result=result_val or "*")
            result_val = result_val if (result_val and result_val != "*") else fallback_meta["result"]
            pgn_date = pgn_date or fallback_meta["pgn_date"]
            site = site or fallback_meta["site"]
            eco = eco or fallback_meta["eco"]

        # A workshop opponent is stored as a shared bot - in the archive we show the personality name.
        if personality_name:
            w_name = personality_name if w_name == CUSTOM_BOT_USERNAME else w_name
            b_name = personality_name if b_name == CUSTOM_BOT_USERNAME else b_name

        items.append({
            "game_id": game_id,
            "white_username": w_name,
            "white_rating": w_rating,
            "black_username": b_name,
            "black_rating": b_rating,
            "status": status_val.value if hasattr(status_val, "value") else str(status_val),
            "is_rated": is_rated,
            "assisted": bool(assisted),
            # Blindfold play (task 19.5): the tier and the number of peeks.
            "blindfold": blindfold_level,
            "peeks": blindfold_peeks,
            "result": result_val or "*",
            "pgn_date": pgn_date,
            "site": site,
            "eco": eco,
            "finished_at": finished_at.isoformat() if finished_at else None,
        })

    return {
        "total": total_count,
        "items": items,
    }


class BlindfoldIn(BaseModel):
    level: int = Field(..., ge=1, le=4)
    peeks: int = Field(0, ge=0, le=10_000)


@router.post("/games/{game_id}/blindfold")
async def mark_blindfold(game_id: int, payload: BlindfoldIn, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    """The "blindfold" mark for a casual game with a human (task 19.5): a participant, the game is finished and unrated."""
    game = await db.get(Game, game_id)
    if not game or current_user.id not in (game.white_player_id, game.black_player_id):
        raise ApiError(404, "game_not_found", game_id=game_id)
    if game.is_rated or game.status != GameStatus.COMPLETED:
        raise ApiError(400, "blindfold_not_allowed")
    game.blindfold_level = max(game.blindfold_level or 0, payload.level)
    game.blindfold_peeks = (game.blindfold_peeks or 0) + payload.peeks
    await db.commit()
    return {"blindfold": game.blindfold_level, "peeks": game.blindfold_peeks}


@router.get("/games/{game_id}/summary")
async def get_game_summary(game_id: int, db: AsyncSession = Depends(get_db)):
    """
    The status and result of a game. Needed by a client that missed game_over (a WebSocket drop at the moment
    of finishing): by this response it finishes the game on its side instead of staying in an "eternal" game.
    """
    game = await db.get(Game, game_id)
    if not game:
        raise ApiError(404, "game_not_found", game_id=game_id)
    return {
        "game_id": game.id,
        "status": game.status.value,
        "result": game.result,
        "termination": game.termination,
        "white_delta": game.white_rating_delta,
        "black_delta": game.black_rating_delta,
    }


@router.get("/games/{game_id}/pgn")
async def download_pgn(game_id: int, db: AsyncSession = Depends(get_db)):
    """
    The game record as a PGN file (games.pgn as is). Open to everyone; the game status is not checked - for a game in progress
    what is already written to the database is returned.
    """
    game = await db.get(Game, game_id)
    if not game or not game.pgn:
        raise ApiError(404, "pgn_not_found", game_id=game_id)

    headers = {"Content-Disposition": f"attachment; filename=regence_game_{game_id}.pgn"}
    return PlainTextResponse(content=game.pgn, media_type="application/x-chess-pgn", headers=headers)


@router.get("/matchmaking/queue")
async def get_matchmaking_queue():
    """Open lobby challenges (from Redis, src/services/matchmaker.get_queue_players). Open to everyone."""
    from src.services.matchmaker import matchmaker
    return await matchmaker.get_queue_players()
