# --- FILE: src/services/ladder.py ---
"""
The club ladder (task 10.4): opponents from weak to strong -- all workshop archetypes (with opponents for
beginners) and all historical bots, ordered by measured strength (src/services/bots/calibration.py), and a separate
player rating in games against them. Progress is a set of passed rungs (the ladder_beaten table, by the opponent's key,
not by number): a new opponent takes its place in the ladder by strength and shifts no one's progress. The current rung is
the first
unpassed one above the strongest passed one (current_index).

Game fairness is checked by the server, not the client. A ladder game is opened by POST /api/v1/bots/ladder/start
(src/api/ladder.py) -- a session in Redis under the key "<scope>:session:<player id>" for LADDER_SESSION_TTL_S. While it is
open (the checks are called by src/api/bots.py):
* a request for an engine move for the player's side (/bots/move, /bots/custom-move) or a position analysis -- a hint;
* a request for a position that has already occurred (the ply does not grow) -- a takeback;
* moves for the opponent by a different bot or a changed config -- opponent substitution.
Such a game is saved to the archive but does not change the rating or the ladder rung -- the player is shown the reason.
A new game while the previous one is unfinished counts the previous one as a loss (otherwise unsuccessful
games could simply be abandoned).

The same mechanism guards a tournament game (task A.2): the session has its own scope (SCOPES) -- "ladder" or
"tournament" -- the move and analysis checks apply to both. A tournament game session is opened by
tournaments.start_player_game; a weekly tournament game against legends (task 26.1) has the scope "weekly"
(src/services/weekly_legends.py).

The ladder rating is the player's ladder_rating and ladder_games fields (User); the module is also called by
src/api/profile.py and
src/services/account.py (erasing progress on account deletion).
"""

import json
import time
from dataclasses import asdict, dataclass
from typing import Literal

import chess
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import redis as redis_module
from src.models.ladder import LadderBeaten
from src.models.user import User
from src.services.bots.archetypes import ARCHETYPES, ARCHETYPES_BY_ID
from src.services.bots.calibration import strength_of
from src.services.bots.personality import BotPersonalityConfig

# Lifetime of a fair game session in Redis (seconds): a game does not last longer, an abandoned one disappears by itself.
LADDER_SESSION_TTL_S = 4 * 3600
# The Elo coefficient of the ladder rating: more mobile for the first K_NEW_GAMES games, then K_ESTABLISHED.
K_NEW = 40
K_ESTABLISHED = 24
K_NEW_GAMES = 10


@dataclass(frozen=True)
class Rung:
    """
    A ladder rung: the opponent's key, its kind, id, strength and a flag that the strength is measured by calibration
    (otherwise -- declared).
    """
    key: str  # "morphy" or "archetype:rusher"
    kind: str  # "historical" | "archetype"
    id: str  # the bot or archetype id: the client takes the name in the player's language from the catalogue
    rating: int
    measured: bool


@dataclass
class LadderSession:
    """
    A fair game session in Redis: the opponent and the player's colour, the greatest ply and the position of the move request
    (to catch a takeback),
    the "game with a hint" reason and the tournament game id (for the "tournament" scope).
    """
    rung_key: str  # the opponent key: a bot id, "archetype:<id>" or "custom:other"
    color: str  # the player's colour
    started_at: float
    max_ply: int = -1
    last_fen: str | None = None
    assisted: str | None = None
    tournament_game_id: int | None = None


# The session scope: "ladder" -- a ladder game, "tournament" -- a tournament game, "weekly" -- a weekly game against
# legends; the Redis key depends on it.
Scope = str
SCOPES: tuple[Scope, ...] = ("ladder", "tournament", "weekly")


def rungs() -> list[Rung]:
    """
    Ladder rungs -- all historical bots and all workshop archetypes, including opponents for beginners (task 7 of
    the plan of 18.11: a single ladder from about 350 to 2400) -- in ascending strength: measured if the bot is calibrated,
    otherwise declared.
    """
    from src.api.bots import AVAILABLE_BOTS

    items = [
        Rung(str(b["id"]), "historical", str(b["id"]), *_strength(str(b["id"]), int(str(b["rating"]))))
        for b in AVAILABLE_BOTS
    ]
    items += [Rung(a.key, "archetype", a.id, *_strength(a.key, a.config.target_elo)) for a in ARCHETYPES]
    return sorted(items, key=lambda r: (r.rating, r.key))


def _strength(key: str, declared: int) -> tuple[int, bool]:
    """The opponent's strength: (rating, whether measured by calibration); without a measurement -- the declared one."""
    s = strength_of(key, declared)
    return s.rating, s.measured


def current_index(items: list[Rung], beaten: set[str]) -> int:
    """
    The current rung: the first unpassed one above the strongest passed one. This way an opponent added below an already
    passed one
    does not throw the player back (it is visible as "skipped" and stays available). All passed -- the last rung.
    """
    top = max((i for i, r in enumerate(items) if r.key in beaten), default=-1)
    return next((i for i in range(top + 1, len(items)) if items[i].key not in beaten), len(items) - 1)


RungStatus = Literal["beaten", "current", "skipped", "locked"]


def rung_status(index: int, rung: Rung, current: int, beaten: set[str]) -> RungStatus:
    """beaten -- passed; current -- the current one; skipped -- weaker than the current but not passed; locked -- ahead."""
    if rung.key in beaten:
        return "beaten"
    if index == current:
        return "current"
    return "skipped" if index < current else "locked"


async def beaten_keys(db: AsyncSession, user_id: int) -> set[str]:
    """The player's passed rungs (the ladder_beaten table)."""
    return set((await db.execute(select(LadderBeaten.rung_key).where(LadderBeaten.user_id == user_id))).scalars())


async def current_rung(db: AsyncSession, user: User) -> tuple[int, Rung]:
    """The player's current rung and its number in rungs()."""
    items = rungs()
    index = current_index(items, await beaten_keys(db, user.id))
    return index, items[index]


def opponent_key(bot_id: str, config: BotPersonalityConfig | None) -> str:
    """The key of the opponent for whom a move was requested: a historical id, an archetype (by config match) or "custom"."""
    if bot_id != "custom":
        return bot_id
    for archetype in ARCHETYPES:
        if config is not None and config == archetype.config:
            return archetype.key
    return "custom:other"


def _key(user_id: int, scope: Scope = "ladder") -> str:
    """The Redis key of the player's session in the scope scope."""
    return f"{scope}:session:{user_id}"


async def get_session(user_id: int, scope: Scope = "ladder") -> LadderSession | None:
    """The player's open session in the scope scope or None."""
    raw = await redis_module.redis_client.get(_key(user_id, scope))
    if not raw:
        return None
    return LadderSession(**json.loads(raw))


async def _store(user_id: int, session: LadderSession, scope: Scope = "ladder") -> None:
    """Writes the session to Redis and extends its lifetime to LADDER_SESSION_TTL_S."""
    await redis_module.redis_client.set(_key(user_id, scope), json.dumps(asdict(session)), ex=LADDER_SESSION_TTL_S)


async def clear_session(user_id: int, scope: Scope = "ladder") -> None:
    """Closes the player's session in the scope scope (the game is over or abandoned)."""
    await redis_module.redis_client.delete(_key(user_id, scope))


async def open_session(
        user_id: int, rung: Rung | str, color: str, scope: Scope = "ladder", tournament_game_id: int | None = None,
) -> LadderSession:
    """Opens a fair game session (rung -- a rung or an opponent key), replacing the previous one in this scope."""
    key = rung if isinstance(rung, str) else rung.key
    session = LadderSession(rung_key=key, color=color, started_at=time.time(), tournament_game_id=tournament_game_id)
    await _store(user_id, session, scope)
    return session


async def _mark(user_id: int, session: LadderSession, reason: str, scope: Scope) -> None:
    """Marks a game as "with a hint"; the first reason is kept."""
    if session.assisted is None:
        session.assisted = reason
    await _store(user_id, session, scope)


async def note_analysis(user_id: int | None) -> None:
    """An engine position analysis during a ladder or tournament game -- a hint."""
    if user_id is None:
        return
    for scope in SCOPES:
        session = await get_session(user_id, scope)
        if session is not None:
            await _mark(user_id, session, "engine_analysis", scope)


async def note_bot_move_request(user_id: int | None, board: chess.Board, requested_key: str) -> None:
    """A bot move request during a ladder or tournament game: a hint, a takeback or opponent substitution."""
    if user_id is None:
        return
    for scope in SCOPES:
        session = await get_session(user_id, scope)
        if session is not None:
            await _note_move(user_id, session, board, requested_key, scope)


async def _note_move(user_id: int, session: LadderSession, board: chess.Board, requested_key: str, scope: Scope) -> None:
    """
    Parses a bot move request: for the player -- a hint, the wrong opponent -- substitution, a position no newer than the
    previous -- a
    takeback; otherwise remembers the ply and the position.
    """
    player_to_move = (board.turn == chess.WHITE) == (session.color == "white")
    if player_to_move:
        await _mark(user_id, session, "engine_hint", scope)
    elif requested_key != session.rung_key:
        await _mark(user_id, session, "opponent_swapped", scope)
    elif board.ply() == session.max_ply and board.fen() == session.last_fen:
        return  # a repeat of the same request (a retry after a connection failure, React's double effect) -- not a takeback
    elif board.ply() <= session.max_ply:
        await _mark(user_id, session, "takeback", scope)
    else:
        session.max_ply = board.ply()
        session.last_fen = board.fen()
        await _store(user_id, session, scope)


def expected_score(rating: int, opponent: int) -> float:
    """The player's expected result by the Elo formula (0..1)."""
    return 1.0 / (1.0 + 10 ** ((opponent - rating) / 400.0))


# Why a game was not counted for the ladder: codes, the text in the player's language is in the client catalogue
# (ladder.reasons).
LADDER_REASONS = ("engine_analysis", "engine_hint", "opponent_swapped", "takeback")


@dataclass
class LadderOutcome:
    """
    The game result for the player: whether counted (counted, otherwise reason), the change and the new rating, the rung and
    the promotion.
    """

    counted: bool
    reason: str | None  # one of LADDER_REASONS
    delta: int
    rating: int
    step: int
    promoted: bool
    opponent: str  # the rung key: "morphy" or "archetype:rusher"


async def apply_result(db: AsyncSession, user: User, rung: Rung, score: float, assisted: str | None) -> LadderOutcome:
    """
    Changes the player's rating and marks the rung as passed (without commit). score -- the player's points: 1, 1/2 or 0. A
    rung
    is credited by a win over the current opponent; a game with a hint (assisted) changes nothing.
    """
    items = rungs()
    beaten = await beaten_keys(db, user.id)
    current = current_index(items, beaten)
    if assisted:
        return LadderOutcome(False, assisted, 0, user.ladder_rating, current, False, rung.key)
    k = K_NEW if user.ladder_games < K_NEW_GAMES else K_ESTABLISHED
    delta = round(k * (score - expected_score(user.ladder_rating, rung.rating)))
    # The ladder rating does not drop below 100.
    user.ladder_rating = max(100, user.ladder_rating + delta)
    user.ladder_games += 1
    promoted = score == 1.0 and items[current].key == rung.key and rung.key not in beaten
    if promoted:
        db.add(LadderBeaten(user_id=user.id, rung_key=rung.key))
        beaten.add(rung.key)
        current = current_index(items, beaten)
    return LadderOutcome(True, None, delta, user.ladder_rating, current, promoted, rung.key)


def find_rung(key: str) -> tuple[int, Rung] | None:
    """The rung by key and its number in rungs(); None -- there is no such opponent."""
    for index, rung in enumerate(rungs()):
        if rung.key == key:
            return index, rung
    return None


def archetype_for(rung: Rung):
    """The workshop archetype for an archetype rung; for a historical bot None."""
    return ARCHETYPES_BY_ID[rung.id] if rung.kind == "archetype" else None
