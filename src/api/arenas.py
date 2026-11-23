# --- FILE: src/api/arenas.py ---
"""
Arenas - tournaments between people (task 17.2): schedule, joining, "Play", table, start reminder. Rules -
src/services/arena.py, schedule by conference - src/services/arena_schedule.py.

Lists and the arena page are open to everyone; joining, "Play" and reminders - only for logged-in users. Arenas, participants
and games
live in the tables arenas, arena_players, arena_games, arena_reminders; who is waiting for a pairing now - in Redis
(arena:{id}:waiting). The arena games themselves go through the shared game WebSocket (src/api/websockets.py).
Monthly arena league (GET /arenas/league) - src/services/arena_league.py.
"""

from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.conferences import SEASON
from src.api.deps import get_current_user
from src.api.fair_play import optional_user_id
from src.core.errors import DomainError
from src.db.session import get_db
from src.models.arena import Arena
from src.models.user import RatingCategory, User
from src.services import arena as service
from src.services import arena_awards, arena_league, conferences
from src.services.matchmaker import MatchmakingError

router = APIRouter()

# How long a finished arena stays visible in the list.
RECENT = timedelta(hours=6)
# HTTP statuses for service refusal codes; all other refusals are 409 (conflict with the arena state).
_CODES = {"arena_not_found": status.HTTP_404_NOT_FOUND, "arena_fair_play": status.HTTP_403_FORBIDDEN,
          "match_wrong_conference": status.HTTP_403_FORBIDDEN, "match_no_conference": status.HTTP_403_FORBIDDEN}


def _http(exc: DomainError):
    return exc.to_http(_CODES.get(exc.code, status.HTTP_409_CONFLICT))


async def _views(db: AsyncSession, rows: list[Arena], now) -> list[dict]:
    """Arena cards of the list: the number of participants and games in progress - two queries for the whole list."""
    players, unfinished = await service.counts(db, [a.id for a in rows])
    return [{**service.view(a, now, unfinished.get(a.id, 0)), "players": players.get(a.id, 0)} for a in rows]


@router.get("")
async def list_arenas(db: AsyncSession = Depends(get_db)):
    """
    Arenas in progress, upcoming (6 hours ahead) and recently finished; the schedule is topped up on request.
    Finished arenas that nobody joined are not shown: with a schedule of five conferences they would clutter the list.
    """
    await service.ensure_schedule(db)
    now = service._now()
    rows = list((await db.execute(
        select(Arena).where(Arena.ends_at > now - RECENT, Arena.starts_at < now + service.LOOKAHEAD)
        .order_by(Arena.starts_at, Arena.id)
    )).scalars().all())
    views = await _views(db, rows, now)
    return {"arenas": [v for v in views if v["status"] != "finished" or v["players"] > 0]}


@router.get("/league")
async def arena_league_table(request: Request, category: RatingCategory = Query("blitz"),
                             season: str | None = Query(None, pattern=SEASON), db: AsyncSession = Depends(get_db)):
    """
    Monthly arena league: players by the sum of arena points of the season (the current month by default) in a time-control
    category. It does not affect
    the rating. Open to everyone; for a logged-in user - their row (me), even if they are below the first rows of the table.
    """
    return await arena_league.league(db, category, season, await optional_user_id(request, db))


@router.get("/current")
async def current_arena(db: AsyncSession = Depends(get_db)):
    """
    For the lobby: an arena that can be joined and played right now (pairings are still being created) - the one with more
    players;
    otherwise the nearest by start time. An arena that is only finishing its games does not go into the announcement.
    """
    await service.ensure_schedule(db)
    now = service._now()
    rows = list((await db.execute(
        select(Arena).where(Arena.ends_at > now, Arena.starts_at < now + service.LOOKAHEAD)
        .order_by(Arena.starts_at, Arena.id)
    )).scalars().all())
    views = await _views(db, rows, now)
    running = [v for v in views if v["status"] == "running"]
    if running:
        return {"arena": max(running, key=lambda v: (v["players"], -v["id"]))}
    upcoming = [v for v in views if v["status"] == "scheduled"]
    return {"arena": upcoming[0] if upcoming else None}


@router.get("/{arena_id}")
async def get_arena(arena_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Arena page: card, table, conference standings and - for a logged-in player - their state (participating or not, waiting for
    a pairing, game in progress, reminder, prize place after the results). It also advances the Swiss: a round may have
    finished.
    """
    user_id = await optional_user_id(request, db)
    try:
        arena = await service.get(db, arena_id)
    except DomainError as exc:
        raise _http(exc) from None
    if arena.format in service.ROUND_FORMATS:
        await service.advance_swiss(db, arena)  # a round may have finished and the tournament may have started
        await db.commit()
    me = None
    if user_id is not None:
        joined = await service._player(db, arena.id, user_id) is not None
        # The player may be in another division of this arena (33.2) - the client will go there.
        division_id = None
        if not joined:
            for item in await service.divisions(db, arena):
                if item.id != arena.id and await service._player(db, item.id, user_id) is not None:
                    division_id = item.id
        me = {"username": getattr(await db.get(User, user_id), "username", None),  # the results find the player's row by name
              "joined": joined, "waiting": user_id in await service.waiting_ids(arena.id),
              "current_game_id": await service.current_game(db, arena.id, user_id) if joined else None,
              "division_arena_id": division_id,
              "reminder": await service.has_reminder(db, arena.id, user_id),
              # Prize place (33.5) - only when awards are handed out, i.e. the results are final.
              "podium_place": await arena_awards.place_of(db, arena.id, user_id) if joined else None}
    return {**service.view(arena, None, await service.open_games(db, arena.id)),
            "standings": await service.standings(db, arena.id),
            # Conference standings of the arena (33.6): the sum of points of the best participants of each conference.
            "conferences": await conferences.arena_table(db, arena.id), "me": me,
            # Conference match: the score of the sides and boards (src/services/conference_match_rules.py).
            "match": await service.match_view(db, arena) if arena.format == "match" else None}


@router.post("/{arena_id}/join")
async def join_arena(arena_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Joining an arena - any registered player without the unfair-play flag; on overflow the player goes into
    another division - its id is in the response.
    """
    try:
        player = await service.join(db, await service.get(db, arena_id), user)
    except DomainError as exc:
        raise _http(exc) from None
    return {"joined": True, "arena_id": player.arena_id}


@router.post("/{arena_id}/remind")
async def remind(arena_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """"Remind me": shortly before the arena starts the player gets a notification (33.4). Only before it starts."""
    try:
        return {"reminder": await service.set_reminder(db, await service.get(db, arena_id), user.id, True)}
    except DomainError as exc:
        raise _http(exc) from None


@router.delete("/{arena_id}/remind")
async def forget_reminder(arena_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Cancel one's own reminder about the arena start."""
    try:
        return {"reminder": await service.set_reminder(db, await service.get(db, arena_id), user.id, False)}
    except DomainError as exc:
        raise _http(exc) from None


@router.post("/{arena_id}/ready")
async def ready(arena_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """
    "Play": a pairing with another waiting player or waiting (the client repeats the request). The waiting mark in Redis is
    considered
    valid for arena.WAIT_TTL_S seconds - whoever stops repeating the request no longer waits.
    """
    try:
        return await service.ready(db, await service.get(db, arena_id), user)
    except MatchmakingError as exc:
        raise exc.to_http(status.HTTP_409_CONFLICT) from None
    except DomainError as exc:
        raise _http(exc) from None


@router.post("/{arena_id}/leave-waiting")
async def leave_waiting(arena_id: int, user: User = Depends(get_current_user)):
    """Stop waiting for a pairing: removes the player from the arena waiting list in Redis."""
    await service.leave_waiting(arena_id, user.id)
    return {"waiting": False}
