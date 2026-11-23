# --- FILE: src/services/arena.py ---
"""
Arenas (task 17.2): time-based tournaments between humans. Rules:

* the schedule is by conference (task 33.4, src/services/arena_schedule.py): arenas are created in advance, LOOKAHEAD
  ahead (lazily — on a list request); empty future arenas that are no longer in the schedule are removed;
* conferences (33.6, src/services/conferences.py): the player's conference is remembered on joining an arena, and their points
  also count towards its standing (the sum of the conference's best participants);
* reminder (33.4): a player pressed "remind me" on an arena that has not started — REMIND_BEFORE before the start they receive
  a
  notification (scheduled task arena_reminders, once a minute);
* joining — until the "last start", including before the start (Swiss — until it is finished); "Play" puts the player into
  waiting (Redis, hash arena:{id}:waiting, the marker lives WAIT_TTL_S seconds), paired with another waiting player closest in
  points and rating, preferably not the previous opponent; the game is an ordinary rated PvP game
  (matchmaker.start_pvp_game), White goes to whoever has played White less often in this arena (on a tie — the one who pressed
  "Play");
* points: win 2, draw 1, loss 0; with FIRE_AFTER wins in a row ("fire") — doubled; a draw or loss breaks the streak;
* fair end (task 33.1, docs/research/arenas.md): new pairs only until the "last start" (end minus the
  game length: 2 x (base + GAME_MOVES x increment)); results are final when the last game has finished (until then
  the status is closing); every game played is counted;
* no-show: the first move is not made and the game is cancelled by timeout — a loss for the side to move, a
  win for the opponent; voluntary cancellation in an arena is forbidden; an agreed draw before EARLY_DRAW_PLIES half-moves — 0
  points for both;
* standings tie-break: performance in the arena, then fewer games, then the earlier joiner;
* entry is open to everyone (owner decision of 17.11.2026, CLAUDE.md, rule 7): any registered
  player joins any arena — without a threshold of games played and without arenas "only up to such-and-such rating". Entry is
  closed
  only to a player with the unfair-play flag. One can join while the arena is not closed for pairing (scheduled / running);
* divisions: a division holds at most DIVISION_SIZE participants; the next joiner goes to the first non-full division
  of the same arena (its own table, the same time and rules), and if there is none — to a new one;
* "berserk" (task 33.3): before their first move the player takes half the base time without increment; a win brings
  BERSERK_BONUS on top of the regular points (after the "fire" doubling). Unavailable in the fastest bullet without increment
  (base
  no more than BERSERK_MIN_BASE_MS — there it is a lottery) and in Swiss; no bonus for a win by the opponent's no-show.

Swiss between humans (format="swiss"): a fixed number of rounds; a round is built by Swiss rules
(tournament_rules.swiss_pairings, seeding by rating at entry), the games of all pairs are created at once (a no-show is a loss
on
time), with an odd number of players — a bye for the weakest player without a bye (points for a win); the next round starts
when
all games of the current one are finished; no "fire". The tournament advances on every game finish and on a page request.

Conference match (format="match", rules in src/services/conference_match_rules.py): the host is conference, the guest is
opponent_conference; only a player of one of the two conferences can sign up, and only until sign-up closes. At the start
the sides line up by rating at entry (arena_players.board), two rounds go in the same order as in Swiss:
the games of all boards are created at once, the next round starts when the current one is finished. Points are as in Swiss (no
"fire", early
draw or berserk); the match score is match_view. There are no trophies for a match (src/services/arena_awards.py).
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DomainError
from src.db import redis as redis_module
from src.models.arena import Arena, ArenaGame, ArenaPlayer, ArenaReminder
from src.models.user import User
from src.services import arena_schedule
from src.services import conference_match_rules as match_rules
from src.services.rating import classify_time_control

# After this many wins in a row the points for the following games are doubled ("fire").
FIRE_AFTER = 2
# Estimated game length in moves: it is used to compute the game duration and the arena's "last start" (game_length).
GAME_MOVES = 40
# Participant cap of one division; the next joiner opens a new division of the same arena.
DIVISION_SIZE = 500
# A draw by agreement before this number of half-moves (20 is 10 moves) brings no points in an arena.
EARLY_DRAW_PLIES = 20
# How many points a win with "berserk" adds.
BERSERK_BONUS = 1
# "Berserk" without increment is available only with a base above this one (a minute): in the 1+0 control it does not exist.
BERSERK_MIN_BASE_MS = 60_000
# How far ahead the scheduled arenas are created (ensure_schedule).
LOOKAHEAD = timedelta(hours=6)
# How long before an arena starts the reminder is sent (send_reminders).
REMIND_BEFORE = timedelta(minutes=5)
# How many seconds the waiting-for-a-pair marker lives: the client repeats "Play", and a player who left drops out of waiting
# by themselves.
WAIT_TTL_S = 120
# Formats that run in rounds (rather than "play while time lasts"): they have their own end (finished_at) and no "fire".
ROUND_FORMATS = ("swiss", "match")


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(moment: datetime) -> datetime:
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment


def game_length(arena: Arena) -> timedelta:
    """How long a game of the arena's time control lasts: both players spend base and increment on GAME_MOVES moves."""
    return timedelta(milliseconds=2 * (arena.base_time_ms + GAME_MOVES * arena.increment_ms))


def last_start(arena: Arena) -> datetime:
    """The last moment when the arena still creates pairs: a game manages to finish by the announced end."""
    return max(_aware(arena.starts_at), _aware(arena.ends_at) - game_length(arena))


def berserk_allowed(arena: Arena) -> bool:
    """Berserk exists in arenas except bullet without increment with a base up to a minute (1+0):
    half a minute without increment is a lottery."""
    if (arena.format or "arena") != "arena":
        return False
    return arena.increment_ms > 0 or arena.base_time_ms > BERSERK_MIN_BASE_MS


def pairing_open(arena: Arena, now: datetime | None = None) -> bool:
    """The arena is creating pairs now: format arena, the start has come, the "last start" has not yet."""
    now = now or _now()
    return (arena.format or "arena") == "arena" and _aware(arena.starts_at) <= now < last_start(arena)


def status(arena: Arena, now: datetime | None = None, open_games: int = 0) -> str:
    """
    scheduled → running (pairs are created) → closing (no more pairs: games are finishing or time remains until the end) →
    finished (the end has come and all games are finished — the results are final). open_games is the number of unfinished
    games
    of the arena, supplied by the caller. Swiss: scheduled → running → finished (when finished_at is recorded, i.e.
    the last round has been played), its announced end does not affect the status.
    """
    now = now or _now()
    if now < _aware(arena.starts_at):
        return "scheduled"
    if arena.format in ROUND_FORMATS:
        return "finished" if arena.finished_at is not None else "running"
    if now < last_start(arena):
        return "running"
    return "closing" if open_games > 0 or now < _aware(arena.ends_at) else "finished"


async def open_games(db: AsyncSession, arena_id: int) -> int:
    """Number of arena games without a result (arena_games.result is empty): in progress or not yet counted."""
    return await db.scalar(select(func.count()).select_from(ArenaGame).where(
        ArenaGame.arena_id == arena_id, ArenaGame.result.is_(None))) or 0


async def ensure_schedule(db: AsyncSession, now: datetime | None = None) -> None:
    """
    Brings the arenas of the nearest LOOKAHEAD in line with the conference schedule: creates missing ones (each — once), and
    removes arenas that have not
    started yet and are no longer in the schedule (it was changed or a conference was disabled) — if nobody
    joined them.
    """
    now = now or _now()
    horizon = max(LOOKAHEAD, match_rules.MATCH_LOOKAHEAD)
    plan: dict[tuple[str, datetime], Arena] = {}
    for item in arena_schedule.planned(now, LOOKAHEAD):
        plan[(item.schedule_key, item.starts_at)] = Arena(
            schedule_key=item.schedule_key, conference=item.conference, base_time_ms=item.slot.base_time_ms,
            increment_ms=item.slot.increment_ms, starts_at=item.starts_at, ends_at=item.ends_at,
            format=item.slot.format, rounds=item.slot.rounds)
    # Conference matches are visible for sign-up in advance — MATCH_LOOKAHEAD ahead.
    slot = match_rules.MATCH_SLOT
    for match in match_rules.planned_matches(now, match_rules.MATCH_LOOKAHEAD, arena_schedule.active_conferences()):
        plan[(match.schedule_key, match.starts_at)] = Arena(
            schedule_key=match.schedule_key, conference=match.home, opponent_conference=match.guest,
            base_time_ms=slot.base_time_ms, increment_ms=slot.increment_ms, starts_at=match.starts_at,
            ends_at=match.ends_at, format=slot.format, rounds=slot.rounds)
    rows = (await db.execute(select(Arena.id, Arena.schedule_key, Arena.starts_at).where(
        Arena.schedule_key.is_not(None), Arena.ends_at > now, Arena.starts_at < now + horizon))).all()
    existing = {(key, _aware(starts_at)) for _, key, starts_at in rows}
    for slot_key, new_arena in plan.items():
        if slot_key not in existing:
            db.add(new_arena)
    stale = [arena_id for arena_id, key, starts_at in rows
             if _aware(starts_at) > now and (key, _aware(starts_at)) not in plan]
    if stale:
        taken = set((await db.execute(select(ArenaPlayer.arena_id).where(ArenaPlayer.arena_id.in_(stale)))).scalars())
        empty = [arena_id for arena_id in stale if arena_id not in taken]
        if empty:
            await db.execute(delete(ArenaReminder).where(ArenaReminder.arena_id.in_(empty)))
            await db.execute(delete(Arena).where(Arena.id.in_(empty)))
    await db.commit()


def points(result_for_player: float, streak_before: int) -> int:
    """
    Points for a game: win 2, draw 1; on "fire" (FIRE_AFTER wins in a row) — doubled. result_for_player is 1.0, 0.5 or
    0.0; streak_before is the player's win streak before this game (in Swiss 0 is passed — there is no "fire" there).
    """
    base = {1.0: 2, 0.5: 1, 0.0: 0}[result_for_player]
    return base * 2 if streak_before >= FIRE_AFTER else base


async def _player(db: AsyncSession, arena_id: int, user_id: int) -> ArenaPlayer | None:
    return (await db.execute(
        select(ArenaPlayer).where(ArenaPlayer.arena_id == arena_id, ArenaPlayer.user_id == user_id)
    )).scalar_one_or_none()


async def get(db: AsyncSession, arena_id: int) -> Arena:
    arena = await db.get(Arena, arena_id)
    if arena is None:
        raise DomainError("arena_not_found")
    return arena


def check_entry(user: User) -> None:
    """
    Admission to an arena: the only condition is fair play. Rating and the number of games played do not affect entry
    (owner decision: no division of players by strength), a newcomer may meet the strongest.
    """
    if user.is_cheater:
        raise DomainError("arena_fair_play")


async def divisions(db: AsyncSession, arena: Arena) -> list[Arena]:
    """All divisions of one arena in order: the first (root) record and records that have it in parent_id."""
    root_id = arena.parent_id or arena.id
    return list((await db.execute(select(Arena).where(
        (Arena.id == root_id) | (Arena.parent_id == root_id)).order_by(Arena.division))).scalars().all())


async def join(db: AsyncSession, arena: Arena, user: User) -> ArenaPlayer:
    """
    Joining an arena: admission, then the first non-full division (or a new one). Already a participant of any division — their
    record, without
    re-checking admission. A finished arena — arena_finished, an arena after the "last start" —
    arena_pairing_closed. The participant record stores the category rating and the conference at the time of joining.
    """
    now = _now()
    if status(arena, now) == "finished":
        raise DomainError("arena_finished")
    if arena.format == "arena" and now >= last_start(arena):
        raise DomainError("arena_pairing_closed")
    from src.services import conferences

    if arena.format == "match":
        existing_player = await _player(db, arena.id, user.id)
        if existing_player:
            return existing_player
        check_match_entry(arena, user, now)
    family = await divisions(db, arena)
    family_ids = [a.id for a in family]
    existing = await db.scalar(select(ArenaPlayer).where(
        ArenaPlayer.arena_id.in_(family_ids), ArenaPlayer.user_id == user.id))
    if existing:
        return existing
    check_entry(user)
    counts = dict((await db.execute(select(ArenaPlayer.arena_id, func.count()).where(
        ArenaPlayer.arena_id.in_(family_ids)).group_by(ArenaPlayer.arena_id))).tuples().all())
    target = next((a for a in family if counts.get(a.id, 0) < DIVISION_SIZE), None)
    if target is None:
        root = family[0]
        target = Arena(schedule_key=None, base_time_ms=root.base_time_ms, increment_ms=root.increment_ms,
                       starts_at=root.starts_at, ends_at=root.ends_at, format=root.format, rounds=root.rounds,
                       division=family[-1].division + 1, parent_id=root.id, conference=root.conference)
        db.add(target)
        await db.flush()
    category = classify_time_control(arena.base_time_ms, arena.increment_ms)
    # The conference is remembered at entry (33.6): a late change of country does not change this arena's standing.
    player = ArenaPlayer(arena_id=target.id, user_id=user.id, rating=user.rating_for(category),
                         conference=conferences.conference_of(user.country))
    db.add(player)
    await db.commit()
    await db.refresh(player)
    return player


def check_match_entry(arena: Arena, user: User, now: datetime) -> None:
    """
    Sign-up for a conference match: fair play, sign-up still open (match_entry_closed), the player has a conference
    (match_no_conference) and it is one of the two sides of the match (match_wrong_conference). There are no strength
    thresholds.
    """
    from src.services import conferences

    check_entry(user)
    if not match_rules.entry_open(_aware(arena.starts_at), now):
        raise DomainError("match_entry_closed")
    conference = conferences.conference_of(user.country)
    if conference is None:
        raise DomainError("match_no_conference")
    if conference not in (arena.conference, arena.opponent_conference):
        raise DomainError("match_wrong_conference")


def _wait_key(arena_id: int) -> str:
    return f"arena:{arena_id}:waiting"


async def leave_waiting(arena_id: int, user_id: int) -> None:
    await redis_module.redis_client.hdel(_wait_key(arena_id), str(user_id))


async def waiting_ids(arena_id: int) -> set[int]:
    """
    Players waiting for a pair in the arena: entries of the Redis hash arena:{id}:waiting (player → marker time) not older than
    WAIT_TTL_S.
    Stale entries are deleted along the way.
    """
    raw = await redis_module.redis_client.hgetall(_wait_key(arena_id))
    now = _now().timestamp()
    alive = {int(uid) for uid, since in raw.items() if now - float(since) < WAIT_TTL_S}
    stale = [uid for uid in raw if int(uid) not in alive]
    if stale:
        await redis_module.redis_client.hdel(_wait_key(arena_id), *stale)
    return alive


async def _last_opponent(db: AsyncSession, arena_id: int, user_id: int) -> int | None:
    row = (await db.execute(
        select(ArenaGame.white_id, ArenaGame.black_id)
        .where(ArenaGame.arena_id == arena_id, (ArenaGame.white_id == user_id) | (ArenaGame.black_id == user_id))
        .order_by(ArenaGame.id.desc()).limit(1)
    )).first()
    if row is None:
        return None
    return row[1] if row[0] == user_id else row[0]


async def _whites(db: AsyncSession, arena_id: int, user_id: int) -> int:
    return await db.scalar(select(func.count()).select_from(ArenaGame).where(
        ArenaGame.arena_id == arena_id, ArenaGame.white_id == user_id)) or 0


async def ready(db: AsyncSession, arena: Arena, user: User) -> dict:
    """
    "Play": the player waits for a pair. If someone else is waiting — a pair and a game at once; otherwise the player stays
    waiting
    (the client repeats the request until a game starts). Returns {"game_id": ...} or {"waiting": true}. If the player already
    has
    a game of this arena in progress (another player formed the pair and the page still repeats the request) — its id, without
    new waiting:
    otherwise the next player to press "Play" would be paired with a busy player.
    """
    from src.services.connection_manager import manager
    from src.services.matchmaker import matchmaker

    now = _now()
    if arena.format != "arena" or now < _aware(arena.starts_at) or now >= _aware(arena.ends_at):
        raise DomainError("arena_not_running")
    if not pairing_open(arena, now):
        raise DomainError("arena_pairing_closed")
    me = await _player(db, arena.id, user.id)
    if me is None:
        raise DomainError("arena_not_joined")
    playing = await current_game(db, arena.id, user.id)
    if playing is not None:
        await leave_waiting(arena.id, user.id)
        return {"game_id": playing}
    await redis_module.redis_client.hset(_wait_key(arena.id), mapping={str(user.id): str(_now().timestamp())})
    others = [uid for uid in await waiting_ids(arena.id) if uid != user.id]
    if not others:
        return {"waiting": True}
    players = {p.user_id: p for p in (await db.execute(
        select(ArenaPlayer).where(ArenaPlayer.arena_id == arena.id, ArenaPlayer.user_id.in_(others))
    )).scalars()}
    last = await _last_opponent(db, arena.id, user.id)

    def distance(uid: int) -> tuple[int, int, int]:
        """The smaller, the better the opponent: first not the previous opponent, then the points gap, then the rating gap."""
        other = players.get(uid)
        if other is None:
            return (2, 0, 0)
        return (int(uid == last), abs(other.score - me.score), abs(other.rating - me.rating))

    opponent_id = min(others, key=distance)
    white, black = (user.id, opponent_id)
    if await _whites(db, arena.id, user.id) > await _whites(db, arena.id, opponent_id):
        white, black = black, white
    await leave_waiting(arena.id, user.id)
    await leave_waiting(arena.id, opponent_id)
    started = await matchmaker.start_pvp_game(white, black, arena.base_time_ms, arena.increment_ms,
                                              connection_manager=manager, db=db, initiator_id=user.id, is_rated=True,
                                              arena=_game_marker(arena))
    db.add(ArenaGame(arena_id=arena.id, game_id=started["game_id"], white_id=white, black_id=black))
    await db.commit()
    return {"game_id": started["game_id"]}


def _game_marker(arena: Arena) -> dict:
    """Arena game marker for the game state and the match_found event: the client uses it to show "berserk"."""
    return {"arena_id": arena.id, "berserk_allowed": berserk_allowed(arena)}


async def is_arena_game(db: AsyncSession, game_id: int) -> bool:
    return await db.scalar(select(ArenaGame.id).where(ArenaGame.game_id == game_id)) is not None


async def game_state_fields(db: AsyncSession, game_id: int) -> dict[str, str]:
    """Arena fields for the game state restored from the database (game_state._recover_state_from_db)."""
    record = (await db.execute(select(ArenaGame).where(ArenaGame.game_id == game_id))).scalar_one_or_none()
    arena = await db.get(Arena, record.arena_id) if record is not None else None
    if record is None or arena is None:
        return {}
    fields = {"arena_id": str(arena.id), "berserk_allowed": "1" if berserk_allowed(arena) else "0"}
    for color in ("white", "black"):
        if getattr(record, f"{color}_berserk"):
            fields[f"{color}_berserk"] = "1"
    return fields


async def berserk(db: AsyncSession, game_id: int, user_id: int) -> dict | None:
    """
    A player's "berserk" in an arena game: a mark in the game record and a new clock in the game state. Returns
    {"color", "state"} (the fresh game state) or None if berserk was already used; a refusal is DomainError.
    """
    from src.models.game import Game
    from src.services.game_state import state_manager

    record = (await db.execute(select(ArenaGame).where(ArenaGame.game_id == game_id))).scalar_one_or_none()
    if record is None or user_id not in (record.white_id, record.black_id):
        raise DomainError("berserk_unavailable")
    res = await state_manager.apply_berserk(game_id, user_id)
    if res["status"] == "error":
        raise DomainError(res["code"])
    if res["status"] != "ok":
        return None
    color = res["color"]
    setattr(record, f"{color}_berserk", True)
    # Copy of the clock in the game record: until the first move nobody updates it, and the state is restored from it.
    game = await db.get(Game, game_id)
    if game is not None:
        setattr(game, f"{color}_time_ms", int(res["state"][f"{color}_time_ms"]))
    await db.commit()
    return {"color": color, "state": res["state"]}


async def on_game_aborted(db: AsyncSession, game_id: int, no_show: str | None) -> bool:
    """
    Arena game cancelled before the first moves (without commit). no_show is the side that did not make the first move: it
    loses,
    the opponent wins with points. None (the side is unknown, e.g. reconciliation after a failure) — the game is closed without
    points so that
    the arena results do not wait for it forever.
    """
    if no_show in ("white", "black"):
        # A win by no-show has no berserk bonus: there was no risk at the board.
        return await on_game_finished(db, game_id, "0-1" if no_show == "white" else "1-0", berserk_bonus=False)
    game = await _locked_game(db, game_id)
    if game is None or game.result is not None:
        return False
    game.result, game.white_points, game.black_points = "*", 0, 0
    return True


async def _locked_game(db: AsyncSession, game_id: int) -> ArenaGame | None:
    """
    The arena game record under a row lock (SELECT ... FOR UPDATE) until the end of the transaction: a second simultaneous
    finish of the same game (the game event and reconciliation after a failure) waits and sees the already recorded result.
    populate_existing — re-read the row even if the object is already in the session.
    """
    return (await db.execute(
        select(ArenaGame).where(ArenaGame.game_id == game_id).with_for_update()
        .execution_options(populate_existing=True)
    )).scalar_one_or_none()


async def on_game_finished(db: AsyncSession, game_id: int, result: str, termination: str | None = None,
                           plies: int | None = None, berserk_bonus: bool = True) -> bool:
    """
    An arena game has finished: points, streaks, counters (without commit). False — this is not an arena game or it is already
    counted.
    result is "1-0", "0-1" or a draw; termination and plies are needed for the early-draw-by-agreement rule;
    berserk_bonus=False — a win without the berserk bonus (opponent's no-show). The game and the rows of both participants are
    taken under
    a lock (ordered by user_id so that crossing transactions do not wait for each other in a circle): points are not lost and
    are not
    awarded twice when games finish simultaneously.
    """
    game = await _locked_game(db, game_id)
    if game is None or game.result is not None:
        return False
    players = {p.user_id: p for p in (await db.execute(
        select(ArenaPlayer).where(ArenaPlayer.arena_id == game.arena_id,
                                  ArenaPlayer.user_id.in_((game.white_id, game.black_id)))
        .order_by(ArenaPlayer.user_id).with_for_update().execution_options(populate_existing=True)
    )).scalars()}
    white_score = {"1-0": 1.0, "0-1": 0.0}.get(result, 0.5)
    # An agreed draw at the very start brings no points (and breaks the streak): the table is for games actually played.
    early_draw = result == "1/2-1/2" and termination == "agreement" and plies is not None and plies < EARLY_DRAW_PLIES
    game.result = result
    sides = ((game.white_id, white_score, "white"), (game.black_id, 1.0 - white_score, "black"))
    arena = await db.get(Arena, game.arena_id)
    swiss = arena is not None and arena.format in ROUND_FORMATS
    for user_id, score, color in sides:
        player = players.get(user_id)
        if player is None:
            continue
        # The early-draw rule is for arenas (in Swiss a round is a round, a draw in it counts as usual).
        earned = 0 if early_draw and not swiss else points(score, 0 if swiss else player.streak)
        if score == 1.0 and berserk_bonus and not swiss and getattr(game, f"{color}_berserk"):
            earned += BERSERK_BONUS
        setattr(game, f"{color}_points", earned)
        player.score += earned
        player.games += 1
        if score == 1.0:
            player.wins += 1
            player.streak += 1
        else:
            player.streak = 0
    return True


async def advance_after_game(db: AsyncSession, game_id: int) -> None:
    """
    After a game has fully finished (its state is already cleared — the players are free) — the next Swiss round. Call
    from game_state after clear_game_state: earlier a new pair will not start ("the player is already in a game").
    """
    record = (await db.execute(select(ArenaGame).where(ArenaGame.game_id == game_id))).scalar_one_or_none()
    if record is None:
        return
    arena = await db.get(Arena, record.arena_id)
    if arena is None or arena.format not in ROUND_FORMATS:
        return
    await advance_swiss(db, arena)  # re-reads the arena under a lock itself
    await db.commit()


# --- Swiss between humans -------------------------------------------------------------------------------

async def advance_swiss(db: AsyncSession, arena: Arena, now: datetime | None = None) -> None:
    """
    Advances a Swiss or a conference match (without commit): after the start — the first round; a round is played — the next
    one or
    the end. Fewer than two participants at the start (for a match — no boards) — the tournament ends without games.

    Atomicity: when a round ends simultaneously on many boards, all who finished games and
    open pages try to advance it. The decision is taken under a lock on the arena row (SELECT ... FOR UPDATE, until the
    caller's
    commit): the first opens the round, the others wait and see the new current_round with unfinished games.
    A cheap check without a lock cuts off the usual case "the round is still going".
    """
    from src.services import tournament_rules as rules

    now = now or _now()
    if arena.format not in ROUND_FORMATS or arena.finished_at is not None or now < _aware(arena.starts_at):
        return
    if await _round_in_progress(db, arena):
        return
    locked = (await db.execute(select(Arena).where(Arena.id == arena.id).with_for_update()
                               .execution_options(populate_existing=True))).scalar_one()
    if locked.finished_at is not None or await _round_in_progress(db, locked):
        return
    games = list((await db.execute(select(ArenaGame).where(ArenaGame.arena_id == arena.id)
                                   .execution_options(populate_existing=True))).scalars())
    players = list((await db.execute(
        select(ArenaPlayer).where(ArenaPlayer.arena_id == arena.id)
        .order_by(ArenaPlayer.rating.desc(), ArenaPlayer.joined_at, ArenaPlayer.id)
        .execution_options(populate_existing=True)
    )).scalars())
    if arena.format == "match":
        await _advance_match(db, arena, players, now)
        return
    if arena.current_round >= arena.rounds or len(players) < 2:
        arena.finished_at = now
        return
    arena.current_round += 1
    seat_of = {p.user_id: i + 1 for i, p in enumerate(players)}
    user_of = {seat: uid for uid, seat in seat_of.items()}
    pairable = list(players)
    if len(pairable) % 2:
        # The bye goes to the lowest by points among those who have not had one yet (with equal points — the lower by seeding);
        # if everyone has had it — the last by seeding.
        bye = min((p for p in pairable if p.byes == 0), key=lambda p: (p.score, -seat_of[p.user_id]), default=pairable[-1])
        bye.byes += 1
        bye.score += points(1.0, 0)
        bye.games += 1
        pairable.remove(bye)
    seats = [seat_of[p.user_id] for p in pairable]
    records = [rules.GameRecord(seat_of[g.white_id], seat_of[g.black_id], g.result)  # type: ignore[arg-type]
               for g in games if g.result and g.white_id in seat_of and g.black_id in seat_of
               and seat_of[g.white_id] in seats and seat_of[g.black_id] in seats]
    for white_seat, black_seat in rules.swiss_pairings(seats, records):
        await _start_swiss_game(db, arena, user_of[white_seat], user_of[black_seat])


async def _advance_match(db: AsyncSession, arena: Arena, players: list[ArenaPlayer], now: datetime) -> None:
    """
    Next round of a conference match (the arena is already under a lock). Before the first round — the lineups: boards by
    rating at
    entry (match_rules.lineup, written to arena_players.board); no boards — the match ends without games. Board
    colours are match_rules.board_colors.
    """
    if arena.current_round == 0:
        order = [p.user_id for p in sorted(players, key=lambda p: (_aware(p.joined_at) if p.joined_at else now, p.id))]
        boards = match_rules.lineup(players, arena.conference or "", arena.opponent_conference or "", order)
        for number, (home, guest) in enumerate(boards, 1):
            home.board = guest.board = number  # type: ignore[attr-defined]
    seated = sorted((p for p in players if p.board), key=lambda p: (p.board, p.conference != arena.conference))
    if arena.current_round >= arena.rounds or not seated:
        arena.finished_at = now
        return
    arena.current_round += 1
    for home, guest in zip(seated[::2], seated[1::2], strict=True):
        home_white = match_rules.board_colors(home.board or 0, arena.current_round)
        white, black = (home, guest) if home_white else (guest, home)
        await _start_swiss_game(db, arena, white.user_id, black.user_id)


async def match_view(db: AsyncSession, arena: Arena) -> dict:
    """
    Conference match for the page: host, guest, side score (win 1, draw 1/2) and boards — pairs of the lineups with the points
    of
    each; before the start the boards are a preliminary lineup by the same rules (there is no arena_players.board record yet).
    """
    rows = (await db.execute(select(ArenaPlayer, User.username).join(User, User.id == ArenaPlayer.user_id)
                             .where(ArenaPlayer.arena_id == arena.id).order_by(ArenaPlayer.joined_at, ArenaPlayer.id))).all()
    name = {p.user_id: username for p, username in rows}
    players = [p for p, _ in rows]
    home_key, guest_key = arena.conference or "", arena.opponent_conference or ""
    if any(p.board for p in players):
        by_board: dict[int, dict[str, ArenaPlayer]] = {}
        for p in players:
            if p.board:
                by_board.setdefault(p.board, {})["home" if p.conference == home_key else "guest"] = p
        pairs = [(by_board[n]["home"], by_board[n]["guest"]) for n in sorted(by_board)]
    else:
        pairs = match_rules.lineup(players, home_key, guest_key, [p.user_id for p in players])  # type: ignore[assignment]

    def seat(p: ArenaPlayer) -> dict:
        return {"username": name[p.user_id], "rating": p.rating, "score": match_rules.side_score(p.score)}

    def total(conference: str) -> float:
        return match_rules.side_score(sum(p.score for p in players if p.conference == conference))

    return {"home": home_key, "guest": guest_key, "home_score": total(home_key), "guest_score": total(guest_key),
            "home_players": sum(p.conference == home_key for p in players),
            "guest_players": sum(p.conference == guest_key for p in players),
            "entry_open": match_rules.entry_open(_aware(arena.starts_at), _now()),
            "boards": [{"board": n, "home": seat(h), "guest": seat(g)} for n, (h, g) in enumerate(pairs, 1)]}


async def _round_in_progress(db: AsyncSession, arena: Arena) -> bool:
    """The current Swiss round has an unfinished game (read from the database, not from session objects)."""
    return bool(await db.scalar(select(func.count()).select_from(ArenaGame).where(
        ArenaGame.arena_id == arena.id, ArenaGame.round == arena.current_round, ArenaGame.result.is_(None))))


async def _start_swiss_game(db: AsyncSession, arena: Arena, white: int, black: int) -> None:
    """A round game; if it could not start (a player is busy with another game) — a draw without play, so the round goes on."""
    from src.models.game import Game, GameStatus
    from src.services.connection_manager import manager
    from src.services.matchmaker import MatchmakingError, matchmaker

    try:
        started = await matchmaker.start_pvp_game(white, black, arena.base_time_ms, arena.increment_ms,
                                                  connection_manager=manager, db=db, is_rated=True,
                                                  arena=_game_marker(arena))
        db.add(ArenaGame(arena_id=arena.id, game_id=started["game_id"], white_id=white, black_id=black,
                         round=arena.current_round))
        await db.flush()
    except MatchmakingError:
        game = Game(white_player_id=white, black_player_id=black, status=GameStatus.ABORTED, is_rated=False)
        db.add(game)
        await db.flush()
        record = ArenaGame(arena_id=arena.id, game_id=game.id, white_id=white, black_id=black, round=arena.current_round)
        db.add(record)
        await db.flush()
        record.result = "1/2-1/2"
        for user_id in (white, black):
            player = await _player(db, arena.id, user_id)
            if player is not None:
                player.games += 1
                player.score += points(0.5, 0)
        record.white_points = record.black_points = points(0.5, 0)


def performance(results: list[tuple[int, float]]) -> int | None:
    """Performance: average opponent rating +- 400 x (wins - losses) / games; no games — None."""
    if not results:
        return None
    total = sum(rating for rating, _ in results)
    balance = sum(1 if score == 1.0 else -1 if score == 0.0 else 0 for _, score in results)
    return round((total + 400 * balance) / len(results))


async def standings(db: AsyncSession, arena_id: int) -> list[dict]:
    """Results table for the arena page — in ranked order; place is the row number."""
    return [{"place": i + 1, "username": name, "score": p.score, "games": p.games, "wins": p.wins,
             "fire": p.streak >= FIRE_AFTER, "rating": p.rating, "performance": perf, "conference": p.conference}
            for i, (p, name, perf) in enumerate(await ranked(db, arena_id))]


async def ranked(db: AsyncSession, arena_id: int) -> list[tuple[ArenaPlayer, str, int | None]]:
    """
    Participants by place: (participant, name, performance). Order: points; on a tie — performance in the arena, then fewer
    games (the same points faster), then the earlier joiner. Games closed without points ("*") do not count towards
    performance.
    Used by the results table and by awards (src/services/arena_awards.py).
    """
    rows = (await db.execute(
        select(ArenaPlayer, User.username).join(User, User.id == ArenaPlayer.user_id)
        .where(ArenaPlayer.arena_id == arena_id)
    )).all()
    rating_of = {p.user_id: p.rating for p, _ in rows}
    results: dict[int, list[tuple[int, float]]] = {uid: [] for uid in rating_of}
    finished = await db.execute(select(ArenaGame).where(
        ArenaGame.arena_id == arena_id, ArenaGame.result.in_(("1-0", "0-1", "1/2-1/2"))))
    for g in finished.scalars():
        white_score = {"1-0": 1.0, "0-1": 0.0}.get(g.result or "", 0.5)
        if g.white_id in results:
            results[g.white_id].append((rating_of.get(g.black_id, 1500), white_score))
        if g.black_id in results:
            results[g.black_id].append((rating_of.get(g.white_id, 1500), 1.0 - white_score))
    perf = {uid: performance(items) for uid, items in results.items()}

    def key(row) -> tuple:
        p = row[0]
        joined = _aware(p.joined_at) if p.joined_at else _now()
        return (-p.score, -(perf[p.user_id] or 0), p.games, joined)

    return [(p, name, perf[p.user_id]) for p, name in sorted(rows, key=key)]


def view(arena: Arena, now: datetime | None = None, open_games: int = 0) -> dict:
    """
    Arena card for the client: time control, start and end, status, last start, whether berserk is available,
    conference, whether it is an evening arena, and division.
    """
    out = {"id": arena.id, "schedule_key": arena.schedule_key, "format": arena.format, "rounds": arena.rounds,
           "current_round": arena.current_round, "base_time_ms": arena.base_time_ms,
           "increment_ms": arena.increment_ms, "starts_at": _aware(arena.starts_at).isoformat(),
           "ends_at": _aware(arena.ends_at).isoformat(), "status": status(arena, now, open_games),
           "open_games": open_games}
    if arena.format == "arena":
        out["last_start_at"] = last_start(arena).isoformat()
    out["berserk"] = berserk_allowed(arena)
    out["conference"] = arena.conference
    out["opponent_conference"] = arena.opponent_conference
    out["evening"] = arena_schedule.is_evening(arena.schedule_key)
    out["division"] = arena.division or 1
    out["parent_id"] = arena.parent_id
    return out


async def current_game(db: AsyncSession, arena_id: int, user_id: int) -> int | None:
    """The player's game in progress in this arena (to move to the board from waiting)."""
    row = await db.scalar(
        select(ArenaGame.game_id).where(
            ArenaGame.arena_id == arena_id, ArenaGame.result.is_(None),
            (ArenaGame.white_id == user_id) | (ArenaGame.black_id == user_id),
        ).order_by(ArenaGame.id.desc()).limit(1)
    )
    return row


async def counts(db: AsyncSession, arena_ids: list[int]) -> tuple[dict[int, int], dict[int, int]]:
    """Number of participants and games in progress per arena — with two queries for the whole list."""
    if not arena_ids:
        return {}, {}
    players = dict((await db.execute(select(ArenaPlayer.arena_id, func.count()).where(
        ArenaPlayer.arena_id.in_(arena_ids)).group_by(ArenaPlayer.arena_id))).tuples().all())
    unfinished = dict((await db.execute(select(ArenaGame.arena_id, func.count()).where(
        ArenaGame.arena_id.in_(arena_ids), ArenaGame.result.is_(None)).group_by(ArenaGame.arena_id))).tuples().all())
    return players, unfinished


# --- Arena start reminders (33.4) ---------------------------------------------------------------------

async def has_reminder(db: AsyncSession, arena_id: int, user_id: int) -> bool:
    return await db.scalar(select(ArenaReminder.id).where(
        ArenaReminder.arena_id == arena_id, ArenaReminder.user_id == user_id)) is not None


async def set_reminder(db: AsyncSession, arena: Arena, user_id: int, on: bool) -> bool:
    """'Remind me' / 'do not remind'. Can be enabled only before the arena starts. Returns whether the reminder is on."""
    if on and status(arena) != "scheduled":
        raise DomainError("arena_reminder_too_late")
    exists = await has_reminder(db, arena.id, user_id)
    if on and not exists:
        db.add(ArenaReminder(arena_id=arena.id, user_id=user_id))
    elif not on and exists:
        await db.execute(delete(ArenaReminder).where(
            ArenaReminder.arena_id == arena.id, ArenaReminder.user_id == user_id))
    await db.commit()
    return on


async def send_reminders(db: AsyncSession, now: datetime | None = None) -> int:
    """
    Notifications to those who asked for a reminder: the arena starts within REMIND_BEFORE (or is already running — if
    the scheduled task was late) and has not ended yet. Each one — once (marker arena_reminders.sent_at). Returns
    the number sent. Without commit: the calling task does it (src/worker/tasks.py).
    """
    from src.services import notifications

    now = now or _now()
    rows = (await db.execute(
        select(ArenaReminder, Arena).join(Arena, Arena.id == ArenaReminder.arena_id)
        .where(ArenaReminder.sent_at.is_(None), Arena.starts_at <= now + REMIND_BEFORE, Arena.ends_at > now)
        .order_by(ArenaReminder.id)
    )).all()
    sent = 0
    for reminder, arena in rows:
        reminder.sent_at = now
        notification = await notifications.record(db, reminder.user_id, "arena_reminder", {
            "arena_id": arena.id, "base_time_ms": arena.base_time_ms, "increment_ms": arena.increment_ms,
            "starts_at": _aware(arena.starts_at).isoformat(),
        })
        await notifications.deliver(reminder.user_id, notification)
        sent += 1
    return sent
