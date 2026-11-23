# --- FILE: src/api/bots.py ---
"""
Bots (/bots): the catalogue of opponents, the bot's move, the reply to a draw offer, saving a played game.

* Who exists: AVAILABLE_BOTS - historical bots and masters with their years of life and declared strength; /catalog adds
  workshop archetypes and the measured strength (calibration.json), /guests - masters of the past from the "Time Machine".
  Names and descriptions in the player's language are in the client catalogues by id.
* Move: /move - a historical bot (src/services/bots/base.py), /custom-move - an opponent built from character settings
  (src/services/bots/personality.py). Both are under the RATE_LIMIT_BOT_MOVE limit and the fair-play rule: during
  one's own game with a human an engine move cannot be obtained. The bot's "thinking" time is computed by the server
  (calculate_authentic_thinking_time_ms), the client keeps the pause.
* A game with a bot runs on the client and is saved in full after it ends (/save-game). The result is determined by the server,
not
  the client: the moves are replayed, the result is taken from the board; resignation gives only a loss to the player; on a
  fallen
  flag the side that has time left wins, and if it cannot deliver mate - a draw. The clocks of a game with a bot run
  on the client, so the server takes the side with the fallen flag from the submitted result
  (resolve_bot_game_outcome). Saving updates the ladder
  (src/services/ladder.py), the tournament (src/services/tournaments.py) and the bot's memory (src/services/bots/memory.py).
* In the users table every bot has its own row with a marker instead of a password - one cannot log in as a bot; workshop
  opponents play under the shared row CUSTOM_BOT_USERNAME, and the personality name is stored in games.personality_name.
"""

import asyncio
import logging
import random
from datetime import UTC, datetime
from typing import Literal

import chess
import chess.pgn
from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, model_validator
from pydantic_core import PydanticCustomError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api import deps
from src.api.fair_play import forbid_engine_help_during_game, optional_user_id
from src.api.personalities import get_owned_personality, personality_config, validate_personality_name
from src.api.rate_limit import rate_limit
from src.core.errors import ApiError, DomainError, DomainValueError, validation_error
from src.db import session as db_session
from src.models.game import Game, GameStatus
from src.models.user import User
from src.services import engine_info, move_check, openings, product_metrics
from src.services import ladder as ladder_service
from src.services import tournaments as tournament_service
from src.services.bots import BOT_INSTANCES  # the single registry of bots (src/services/bots/__init__.py)
from src.services.bots import calibration as bot_calibration
from src.services.bots import memory as bot_memory
from src.services.bots import selfplay as bot_selfplay
from src.services.bots.archetypes import ARCHETYPES, ARCHETYPES_BY_ID, ARCHETYPES_BY_KEY
from src.services.bots.guests import GUESTS, GUESTS_BY_ID, GUESTS_BY_PGN_NAME, SIGNATURE_OPENINGS
from src.services.bots.masters import MASTERS
from src.services.bots.personality import DRAW_OFFER_MIN_MOVE, BotPersonalityConfig, PersonalityBot, draw_answer
from src.services.bots.philidor import resolve_stockfish_path
from src.services.engine_pool import engine_work
from src.services.game_engine import board_from_start_fen, flag_outcome, is_standard_start, terminal_outcome
from src.services.rating import classify_time_control
from src.services.task_dispatch import schedule_game_analysis_in_background, schedule_tournament_simulations_in_background

router = APIRouter()

# The same dependencies as in the other sections: get_db - the database session per request (src/db/session.py),
# get_current_user - the logged-in player (src/api/deps.py).
get_db = getattr(deps, "get_db", None) or getattr(db_session, "get_db", None)
get_current_user = getattr(deps, "get_current_user", None)

# Historical bots. The name, title and motto in the player's language are in the client catalogues (bots.profiles.<id>);
# here is data: id (also the bot user's name in the database), the PGN name (Latin, as in game archives),
# years, declared strength, portrait.
AVAILABLE_BOTS = [
    {
        "id": "philidor",
        "pgn_name": "Philidor, François-André",
        "era": "1749–1795",
        "rating": 1850,
        "avatar": "/assets/champions/philidor.jpg",
    },
    {
        "id": "labourdonnais",
        "pgn_name": "La Bourdonnais, Louis-Charles",
        "era": "1795–1840",
        "rating": 1950,
        "avatar": "/assets/champions/labourdonnais.jpg",
    },
    {
        "id": "staunton",
        "pgn_name": "Staunton, Howard",
        "era": "1810–1874",
        "rating": 2000,
        "avatar": "/assets/champions/staunton.jpg",
    },
    {
        "id": "anderssen",
        "pgn_name": "Anderssen, Adolf",
        "era": "1818–1879",
        "rating": 2100,
        "avatar": "/assets/champions/anderssen.jpg",
    },
    {
        "id": "morphy",
        "pgn_name": "Morphy, Paul",
        "era": "1837–1884",
        "rating": 2150,
        "avatar": "/assets/champions/morphy.jpg",
    },
    {
        "id": "paulsen",
        "pgn_name": "Paulsen, Louis",
        "era": "1833–1891",
        "rating": 2080,
        "avatar": "/assets/champions/paulsen.jpg",
    },
    {
        "id": "zukertort",
        "pgn_name": "Zukertort, Johannes",
        "era": "1842–1888",
        "rating": 2120,
        "avatar": "/assets/champions/zukertort.jpg",
    },
    # Second-wave masters (task 21.5): portraits come from the champions section; since 18.11 they are ladder rungs, like all
    # bots.
    *({"id": m.id, "pgn_name": m.pgn_name, "era": m.era, "rating": m.rating,
       "avatar": f"/assets/champions/{m.id.capitalize()}.jpg"} for m in MASTERS),
]

logger = logging.getLogger(__name__)

BOT_METADATA = {b["id"]: b for b in AVAILABLE_BOTS}

# A service "hash" in hashed_password by which the account is recognised as a bot.
# It is not a valid bcrypt hash, so logging in as a bot is impossible.
BOT_PASSWORD_MARKER = "!historical_bot_no_login!"


# The shared bot user for games with workshop personalities: in the database the opponent is it,
# while the PGN and the archive show the personality name (games.personality_name).
CUSTOM_BOT_ID = "custom"
CUSTOM_BOT_USERNAME = "workshop_opponent"
CUSTOM_BOT_RATING = 1500


def reserved_bot_usernames() -> set[str]:
    """Names (and ids) of bots that cannot be taken at registration (compared case-insensitively)."""
    names: set[str] = {CUSTOM_BOT_USERNAME.casefold()}
    for bot in AVAILABLE_BOTS:
        names.add(str(bot["id"]).casefold())
    # Archetype key names in the archive ("archetype:rusher") are rejected by the name rules anyway (the colon),
    # but the archetype ids themselves cannot be taken, so that a player cannot impersonate a ladder opponent.
    names.update(archetype_id.casefold() for archetype_id in ARCHETYPES_BY_ID)
    return names


# The "thinking" pace of first-wave historical bots: a multiplier of the time per move (below 1 - plays faster).
# The numbers are set by hand; other bots and workshop opponents have multiplier 1.
BOT_TEMPO_MULTIPLIER = {
    "morphy": 0.72,
    "labourdonnais": 0.78,
    "anderssen": 0.90,
    "philidor": 0.95,
    "zukertort": 1.00,
    "paulsen": 1.22,
    "staunton": 1.28,
}


class BotMoveRequest(BaseModel):
    """Request for a historical bot's move (POST /bots/move): who moves and in which position."""
    bot_id: str = Field(default="philidor", description="ID of the historical bot")
    fen: str = Field(..., max_length=100, description="Current position on the board in FEN format")


class BotComment(BaseModel):
    """A bot remark: a botComments catalogue key on the client and parameters (the text in the player's language is there)."""
    key: str
    params: dict[str, int | str] = Field(default_factory=dict)


class BotMoveResponse(BaseModel):
    """
    The bot's move: the move record, the position after it, the source of the move (source: opening book or engine), the bot's
    remark and
    the "thinking" time that the client keeps before showing the move.
    """
    bot_id: str
    uci: str
    san: str
    fen_after: str
    source: str
    comment: BotComment
    thinking_time_ms: int = Field(default=650, description="Recommended bot thinking time in ms")


class CustomBotMoveRequest(BaseModel):
    """
    A request for a workshop opponent's move: the position and either character settings or the id of a saved personality (not
    both
    at once).
    """
    config: BotPersonalityConfig | None = Field(
        default=None, description="Opponent character (sliders, piece weights, strength); balanced by default",
    )
    personality_id: int | None = Field(
        default=None, description="A saved personality of the player (login required) - instead of config",
    )
    fen: str = Field(..., max_length=100, description="Current position on the board in FEN format")

    @model_validator(mode="after")
    def _config_or_saved(self) -> CustomBotMoveRequest:
        if self.config is not None and self.personality_id is not None:
            raise validation_error("config_or_personality")
        return self


class BotGameSaveRequest(BaseModel):
    """
    A played game with a bot to be saved: the opponent, the player's colour, moves, the claimed result, time control and flags
    of
    a special game (ladder, tournament, mentor, blindfold, custom start position). The result is determined by the server
    itself.
    """
    bot_id: str = Field(..., description="ID of the historical bot or 'custom' - a personality from the workshop")
    personality_id: int | None = Field(default=None, description="For bot_id='custom': a saved personality")
    personality_name: str | None = Field(
        default=None, min_length=3, max_length=30,
        description="For bot_id='custom' without saving: the opponent name from the constructor",
    )
    ladder: bool = Field(default=False, description="A club ladder game (opened by POST /bots/ladder/start)")
    tournament_game_id: int | None = Field(default=None, description="The player's tournament game (task 15.3)")
    assisted: bool = Field(default=False, description="The player used the mentor: a training game")
    blindfold: int | None = Field(default=None, ge=1, le=4, description="Blindfold play (task 19.5): tier 1-4")
    peeks: int = Field(default=0, ge=0, le=10_000, description="How many times the player peeked at the position")
    player_color: str = Field(..., description="The player's colour ('white' or 'black')")
    result: str = Field(..., description="Game result ('1-0', '0-1', '1/2-1/2')")
    termination: str | None = Field(
        default=None,
        description="For a position not finished on the board: 'resignation' (the player resigned), 'timeout' (flag fell) or "
                    "'agreement' (the bot accepted a draw, task 21.4; not for ladder and tournament)",
    )
    moves_uci: list[str] = Field(default_factory=list, max_length=1000, description="List of moves made in UCI format")
    start_fen: str | None = Field(
        default=None, max_length=120,
        description="Starting position of the game (FEN), if it did not start from the standard setup",
    )
    # Bounds - so that a value from the request fits an INTEGER column and does not cause a 500.
    base_time_ms: int = Field(default=180000, ge=1000, le=86_400_000, description="Base time control in ms")
    increment_ms: int = Field(default=0, ge=0, le=3_600_000, description="Time increment per move in ms")


class BotGameSaveResponse(BaseModel):
    """
    The save response: the game id and its result, the outcome for the ladder, the tournament and the reason for a technical
    loss in it,
    the rating change.
    """
    game_id: int
    status: str
    result: str
    ladder: ladder_service.LadderOutcome | None = None
    tournament_id: int | None = None
    # The reason for a loss in a tournament instead of the board result (a code, as for the ladder: engine_hint, takeback,
    # coach...).
    tournament_forfeit: str | None = None
    # All tournaments are rated (15.4): the change of the player's rating in the tournament's time-control category.
    rating_before: int | None = None
    rating_after: int | None = None
    rating_delta: int | None = None


def calculate_authentic_thinking_time_ms(
        bot_id: str,
        board: chess.Board,
        uci_move: str,
        source: str,
) -> int:
    """
    Computes a realistic human time per move (in ms) for a historical master
    taking into account his pace, the opening book, a single reply or the tactical complexity of the position.

    This is an imitation for the client, not the engine's running time: a single move - about 0.3 s, a book move - 0.4-0.7 s
    plus a little with each move of the game, the others - from 0.32 to 2.9 s (more moves and captures on the board, a check or
    a capture - longer; with ten pieces or fewer - faster). The value has a random component.
    """
    legal_moves = list(board.legal_moves)
    num_legal = len(legal_moves)
    tempo = BOT_TEMPO_MULTIPLIER.get(bot_id, 1.0)

    if num_legal <= 1:
        return int(random.randint(240, 380) * tempo)

    if source in ("book", "opening_book"):
        base_ms = random.randint(360, 680) + board.fullmove_number * 22
        return int(base_ms * tempo)

    move_obj = chess.Move.from_uci(uci_move)
    is_capture = board.is_capture(move_obj)
    gives_check = board.gives_check(move_obj)

    captures_available = sum(1 for m in legal_moves if board.is_capture(m))
    complexity_ms = min(num_legal * 26, 950) + min(captures_available * 95, 550)

    if board.is_check():
        complexity_ms += 250
    if is_capture or gives_check:
        complexity_ms += 280

    piece_count = len(board.piece_map())
    if piece_count <= 10:
        complexity_ms = int(complexity_ms * 0.65)

    raw_ms = (520 + complexity_ms + random.randint(-110, 180)) * tempo
    return max(320, min(int(raw_ms), 2900))


def _replay_moves(moves_uci: list[str], start_fen: str | None = None) -> chess.Board:
    """
    Replays moves with history (needed for repetition rules) from the standard setup or
    from start_fen; ValueError for an illegal move or an impossible starting position.
    """
    board = board_from_start_fen(start_fen)
    for uci_str in moves_uci:
        try:
            move = chess.Move.from_uci(uci_str)
        except ValueError:
            raise DomainValueError("invalid_history_move", move=uci_str) from None
        if move not in board.legal_moves:
            raise DomainValueError("illegal_history_move", move=uci_str)
        board.push(move)
    return board


def resolve_bot_game_outcome(board: chess.Board, payload: BotGameSaveRequest) -> tuple[str, str]:
    """
    The result of a game with a bot is determined by the server, not the client:
    - the position on the board is final (mate, stalemate, repetition, ...) - the result from the board;
    - the player resigned - only a loss for the player;
    - the flag fell - a win for the side whose flag did not fall, but a draw if it has no material
      to mate (FIDE rule 6.9). The clocks of a game with a bot live on the client, so the side
      with the fallen flag is taken by the server from the submitted result;
    - the bot agreed to a draw (termination='agreement') - a draw. The server does not remember the agreement and cannot verify
      it, so in ladder and tournament games such a result is not accepted (the check is in save_bot_game).
    Otherwise the game is not finished, and a "win" cannot be saved.
    Returns (result, termination reason).
    """
    outcome = terminal_outcome(board)
    if outcome is not None:
        return outcome

    if payload.termination == "resignation":
        return ("0-1" if payload.player_color == "white" else "1-0"), "resignation"

    if payload.termination == "agreement":
        return "1/2-1/2", "agreement"

    if payload.termination == "timeout":
        if payload.result == "1-0":
            return flag_outcome(board.fen(), "black")
        if payload.result == "0-1":
            return flag_outcome(board.fen(), "white")
        raise DomainValueError("flag_winner_required")

    raise DomainValueError("termination_required")


def _build_pgn_string(
        moves_uci: list[str],
        white_name: str,
        white_elo: int,
        black_name: str,
        black_elo: int,
        result: str,
        start_fen: str | None = None,
) -> tuple[str, str]:
    """Builds a valid PGN document with headers and returns (pgn_text, final_fen)."""
    board = board_from_start_fen(start_fen)
    custom_start = not is_standard_start(board)
    pgn_game = chess.pgn.Game()
    if custom_start:
        # The SetUp/FEN headers are the standard way to record a game that does not start from the initial setup.
        pgn_game.setup(board)
    pgn_game.headers["Event"] = "Historical Bot Match"
    pgn_game.headers["Site"] = "Regence Bot Arena"
    pgn_game.headers["Date"] = datetime.now(UTC).strftime("%Y.%m.%d")
    pgn_game.headers["Round"] = "-"
    pgn_game.headers["White"] = white_name
    pgn_game.headers["Black"] = black_name
    pgn_game.headers["Result"] = result
    pgn_game.headers["WhiteElo"] = str(white_elo)
    pgn_game.headers["BlackElo"] = str(black_elo)
    if not custom_start:
        pgn_game.headers["ECO"] = openings.eco_code(moves_uci)

    node: chess.pgn.GameNode = pgn_game
    for uci_str in moves_uci:
        move = chess.Move.from_uci(uci_str)
        if move not in board.legal_moves:
            raise DomainValueError("illegal_history_move", move=uci_str)
        board.push(move)
        node = node.add_variation(move)

    exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=False)
    return pgn_game.accept(exporter).strip(), board.fen()


async def _get_or_create_bot_user(db: AsyncSession, bot_id: str) -> User:
    """Finds or creates the bot record in the users table (a historical one or the one shared by personalities)."""
    if bot_id == CUSTOM_BOT_ID:
        bot_username, bot_rating = CUSTOM_BOT_USERNAME, CUSTOM_BOT_RATING
    else:
        bot_username, bot_rating = bot_id, int(str(BOT_METADATA[bot_id]["rating"]))

    stmt = select(User).where(User.username == bot_username)
    res = await db.execute(stmt)
    bot_user = res.scalar_one_or_none()
    if bot_user is not None:
        if bot_user.is_bot:
            return bot_user
        # The name is taken by a human (before the ban on registering bot names) - we do not attribute
        # the bot's games to them, but create the bot under a service name.
        bot_username = f"{bot_username}_bot"
        res = await db.execute(select(User).where(User.username == bot_username))
        bot_user = res.scalar_one_or_none()
        if bot_user is not None:
            return bot_user

    bot_user = User(
        username=bot_username,
        hashed_password=BOT_PASSWORD_MARKER,
        # The bot's fixed "historical strength" - the same in all categories: this is a purely displayed
        # value, the bot's own rating is not changed by games. Games with a bot are not rated (is_rated=False), except
        # tournament ones - there only the player's rating changes.
        bullet_rating=bot_rating,
        blitz_rating=bot_rating,
        rapid_rating=bot_rating,
        classical_rating=bot_rating,
        is_bot=True,
    )
    db.add(bot_user)
    await db.flush()
    return bot_user


def _prepare_game_kwargs(
        white_id: int,
        black_id: int,
        pgn_text: str,
        final_fen: str,
        payload: BotGameSaveRequest,
) -> dict:
    """Builds the dictionary of Game model fields for a finished game with a bot."""
    now_utc = datetime.now(UTC)
    return {
        "white_player_id": white_id,
        "black_player_id": black_id,
        "pgn": pgn_text,
        "board_fen": final_fen,
        "result": payload.result,
        "termination": payload.termination or "normal",
        "is_rated": False,
        "base_time_ms": payload.base_time_ms,
        "increment_ms": payload.increment_ms,
        "status": GameStatus.COMPLETED,
        "finished_at": now_utc,
        "pgn_date": now_utc.strftime("%Y.%m.%d"),
        "site": "Regence Bot Arena",
        # A game from an arbitrary position has no opening.
        "eco": None if payload.start_fen else openings.eco_code(payload.moves_uci),
    }


def _playable_board(fen: str) -> chess.Board:
    """A position in which the bot has something to move; otherwise 400."""
    try:
        board = chess.Board(fen)
    except ValueError:
        raise ApiError(400, "invalid_fen") from None

    # chess.Board also accepts impossible positions (no king, kings adjacent, the side that has just
    # moved is in check) - the engine may crash on them and drop out of the pool.
    if not board.is_valid():
        raise ApiError(400, "invalid_position")

    if board.is_game_over():
        raise ApiError(400, "game_already_over")
    return board


@router.get("/engine")
async def get_engine_info():
    """
    The engine of this installation for "About" (task 23.1): version, GPL-3.0 licence and the sources of exactly this version.
    Information that is harmless to fair play - no evaluations, no moves.
    """
    return await asyncio.to_thread(engine_info.describe, resolve_stockfish_path())


PUBLIC_LIMIT = Depends(rate_limit("public_api", "RATE_LIMIT_PUBLIC_API", code="public_api_rate_limited"))


@router.get("/calibration/runs", dependencies=[PUBLIC_LIMIT])
async def get_calibration_runs():
    """Calibration run logs (task 24.3): match protocols and games - as recorded during the run."""
    return {"calibration": bot_calibration.load_calibration().get("meta"), "runs": bot_calibration.runs()}


@router.get("/calibration/runs/{name}", response_class=PlainTextResponse, dependencies=[PUBLIC_LIMIT])
async def get_calibration_run(name: str = Path(..., max_length=80)):
    """
    One calibration run log as text (PGN of games or a match protocol) - the file written by
    scripts/calibrate_bots.py; 404 if there is no such log. Open to everyone, under the open API limit.
    """
    text = await asyncio.to_thread(bot_calibration.read_run, name)
    if text is None:
        raise ApiError(404, "calibration_run_not_found")
    return PlainTextResponse(text, media_type="application/x-chess-pgn" if name.endswith(".pgn") else "text/plain")


@router.get("/catalog")
async def get_bot_catalog(db: AsyncSession = Depends(get_db)):
    """
    Bot strength and workshop archetypes: the declared rating and the one measured by matches with Stockfish anchors
    (scripts/calibrate_bots.py), if calibration has already been run. Historical bots also have live: the rating from games
    with
    humans, their number and the engine strength correction (task 32.1).
    """
    def strength(key: str, declared: int) -> dict:
        s = bot_calibration.strength_of(key, declared)
        return {"declared_rating": declared, "rating": s.rating, "measured": s.measured,
                "games": s.games, "ci95": s.ci95}

    live = await bot_memory.live_strength(db)
    # Archetypes - with strength sliders tuned by self-play (task 32.3).
    await bot_selfplay.refresh(db)

    def live_of(key: str) -> dict | None:
        row = live.get(key)
        return {"rating": round(row.rating), "games": row.games, "offset": row.offset} if row else None

    return {
        "calibration": bot_calibration.load_calibration().get("meta"),
        "historical": [{"id": b["id"], **strength(str(b["id"]), int(str(b["rating"]))), "live": live_of(str(b["id"]))}
                       for b in AVAILABLE_BOTS],
        "archetypes": [
            {"id": a.id, "config": bot_selfplay.tuned_config(a).model_dump(), **strength(a.key, a.config.target_elo)}
            for a in ARCHETYPES
        ],
    }


@router.get("/tuning-log", dependencies=[PUBLIC_LIMIT])
async def get_tuning_log(db: AsyncSession = Depends(get_db)):
    """Open log of character tuning by self-play (task 32.3): what was measured and how the strength sliders were shifted."""
    rows = await bot_selfplay.journal(db)
    return {"entries": [{
        "key": r.key, "created_at": r.created_at.isoformat() if r.created_at else None, "games": r.games,
        "measured": r.measured, "target": r.target, "randomness": [r.randomness_before, r.randomness_after],
        "blunder_guard_cp": [r.guard_before, r.guard_after],
    } for r in rows], "rules": {"games": bot_selfplay.TUNE_GAMES, "drift": bot_selfplay.DRIFT}}


@router.get("/rivalry")
async def get_rivalry(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Which historical bots remember the player (task 32.2): how many games and how many points the bot scored in them."""
    rivals = await bot_memory.rivals_of(db, current_user.id)
    return {"rivals": [{"bot_id": r.bot_id, "games": r.games, "bot_points": r.points,
                        "remembers": r.games >= bot_memory.RIVAL_MIN_GAMES} for r in rivals]}


@router.get("/guests", dependencies=[PUBLIC_LIMIT])
async def get_guests():
    """
    Masters of the past - a catalogue of opponents (task 28.5): participants of the "Time Machine" tournaments, each can be
    played in
    a separate game. The server serves keys and numbers: the name and the line about the master are taken by the client from
    the catalogue by id, tournament
    names - by keys; signature openings - names from the open openings table.
    """
    from src.services import time_machine

    events_of: dict[str, list[str]] = {}
    for event in time_machine.EVENTS:
        for entry in event.field:
            events_of.setdefault(entry.id, []).append(event.key)
    guests = []
    for guest in GUESTS:
        white, black = SIGNATURE_OPENINGS.get(guest.id, ((), ()))
        guests.append({
            "id": guest.id, "pgn_name": guest.pgn_name, "era": guest.era, "rating": guest.rating,
            "events": events_of.get(guest.id, []), "openings": {"white": list(white), "black": list(black)},
        })
    return {"guests": guests}


@router.get("/guests/{guest_id}", dependencies=[PUBLIC_LIMIT])
async def get_guest(guest_id: str = Path(..., max_length=40)):
    """The character of a master of the past - to start a game with him: the same one he plays with in the historical
    tournament."""
    guest = GUESTS_BY_ID.get(guest_id)
    if guest is None:
        raise ApiError(404, "guest_not_found")
    return {"id": guest.id, "pgn_name": guest.pgn_name, "rating": guest.rating, "config": guest.config.model_dump()}


class DrawOfferRequest(BaseModel):
    """
    A draw offer to a bot: the position, who the opponent is and which colour it plays; for a workshop opponent - its
    character (config) or the id of a saved personality.
    """
    fen: str = Field(..., max_length=100)
    bot_id: str = Field(..., max_length=40)
    bot_color: Literal["white", "black"]
    config: BotPersonalityConfig | None = None
    personality_id: int | None = None


# The attitude of historical masters to a draw (task 21.4): attacking romantics agree reluctantly.
HISTORICAL_DRAW_ATTITUDE = {"labourdonnais": -40, "anderssen": -60, "morphy": -40, "zukertort": -20}


@router.post("/draw-offer", dependencies=[
    Depends(rate_limit("bot_move", "RATE_LIMIT_BOT_MOVE")),
    Depends(forbid_engine_help_during_game),
])
async def draw_offer(payload: DrawOfferRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """
    The bot's reply to a draw offer (task 21.4): by the evaluation of the position for the bot and its attitude to a draw. In
    the opening
    (before move 10, personality.DRAW_OFFER_MIN_MOVE) the bot does not agree - the game has not really started - and the engine
    is not
    called. The evaluation is taken from the evaluation cache or computed by the engine (move_check.evaluate_cached); it is an
    evaluation
    of the position, so the endpoint is closed by the fair-play rule and the bot move limit. The server does not remember the
    agreement.
    """
    board = _playable_board(payload.fen)
    if payload.bot_id == CUSTOM_BOT_ID:
        config = payload.config or BotPersonalityConfig()
        if payload.personality_id is not None:
            owner = await _bearer_user(request, db)
            config = personality_config(await get_owned_personality(db, owner.id, payload.personality_id))
    elif payload.bot_id in BOT_INSTANCES:
        config = BotPersonalityConfig(draw_attitude=HISTORICAL_DRAW_ATTITUDE.get(payload.bot_id, 0))
    else:
        raise ApiError(404, "bot_not_found", bot_id=payload.bot_id)
    score = None
    if board.fullmove_number >= DRAW_OFFER_MIN_MOVE:
        evaluation = await move_check.evaluate_cached(board)
        if evaluation is None:
            raise ApiError(503, "engine_busy", headers={"Retry-After": "5"})
        score = evaluation.cp_white if payload.bot_color == "white" else -evaluation.cp_white
    accepted, comment = draw_answer(config, score, board.fullmove_number)
    return {"accepted": accepted, "comment": comment}


@router.get("/openings")
async def search_openings(q: str = Query("", max_length=60), epd: list[str] = Query(default_factory=list, max_length=120)):
    """
    Openings for the workshop (task 21.2): search by name or ECO code, or entries by positions (EPD) - to
    show the names of the already chosen ones. The names are English proper names from the open table.
    """
    table = openings.lines()
    found = [table[key] for key in epd if key in table] if epd else openings.search(q)
    return {"openings": [{"eco": o.eco, "name": o.name, "epd": o.epd, "moves": list(o.moves)} for o in found]}


@router.get("/list")
async def get_available_bots():
    """
    Returns the list of available historical bots (AVAILABLE_BOTS) and the Stockfish engine status: whether its
    binary is found on this server. Open to everyone.
    """
    return {
        "bots": AVAILABLE_BOTS,
        "stockfish_active": bool(resolve_stockfish_path()),
    }


@router.post(
    "/move",
    response_model=BotMoveResponse,
    # A bot move in an arbitrary position is the same engine hint as analysis.
    dependencies=[
        Depends(rate_limit("bot_move", "RATE_LIMIT_BOT_MOVE")),
        Depends(forbid_engine_help_during_game),
    ],
)
async def get_bot_move(payload: BotMoveRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Takes the FEN of a position and returns the reply move of the chosen historical bot. Available to a guest too. Before the
    move:
    the request is noted in the player's ladder or tournament session (a hint, takeback or opponent swap -
    src/services/ladder.py), the bot loads its memory (opening results, and in the opening also the memory of this opponent,
    src/services/bots/memory.py). The move choice itself is a synchronous computation in a separate thread.
    """
    bot = BOT_INSTANCES.get(payload.bot_id)
    if bot is None:
        raise ApiError(404, "bot_not_found", bot_id=payload.bot_id)

    board = _playable_board(payload.fen)
    user_id = await optional_user_id(request, db)
    await ladder_service.note_bot_move_request(user_id, board, payload.bot_id)
    await bot_memory.refresh(db, payload.bot_id)
    # The memory of the opponent (task 32.2) is needed only in the opening - while the bot plays by the book.
    in_opening = (board.fullmove_number - 1) * 2 + (board.turn == chess.BLACK) < bot_memory.BOOK_PLIES
    bot_memory.use_rival(await bot_memory.load_rival(db, payload.bot_id, user_id) if in_opening else None)
    with engine_work("bot_move"):
        result = await asyncio.to_thread(bot.choose_move, payload.fen)
    thinking_time_ms = calculate_authentic_thinking_time_ms(
        bot_id=payload.bot_id,
        board=board,
        uci_move=result["uci"],
        source=result["source"],
    )

    return BotMoveResponse(
        bot_id=payload.bot_id,
        uci=result["uci"],
        san=result["san"],
        fen_after=result["fen_after"],
        source=result["source"],
        comment=result["comment"],
        thinking_time_ms=thinking_time_ms,
    )


@router.post(
    "/custom-move",
    response_model=BotMoveResponse,
    # A limit shared with /move: the same load on Stockfish and the same engine hint.
    dependencies=[
        Depends(rate_limit("bot_move", "RATE_LIMIT_BOT_MOVE")),
        Depends(forbid_engine_help_during_game),
    ],
)
async def get_custom_bot_move(
        payload: CustomBotMoveRequest, request: Request, db: AsyncSession = Depends(get_db),
):
    """
    The move of an opponent built from character sliders (src/services/bots/personality.py): the character is sent in
    the request (available to a guest) or taken from the player's saved personality (login required, someone else's - 404). The
    request is likewise
    noted in the ladder or tournament session.
    """
    board = _playable_board(payload.fen)
    config = payload.config
    if payload.personality_id is not None:
        owner = await _bearer_user(request, db)
        config = personality_config(await get_owned_personality(db, owner.id, payload.personality_id))
    bot = PersonalityBot(config or BotPersonalityConfig())
    await ladder_service.note_bot_move_request(
        await optional_user_id(request, db), board,
        ladder_service.opponent_key("custom", None if payload.personality_id is not None else bot.config),
    )
    with engine_work("bot_move"):
        result = await asyncio.to_thread(bot.choose_move, payload.fen)
    return BotMoveResponse(
        bot_id=bot.bot_id,
        uci=result["uci"],
        san=result["san"],
        fen_after=result["fen_after"],
        source=result["source"],
        comment=result["comment"],
        thinking_time_ms=calculate_authentic_thinking_time_ms(
            bot_id=bot.bot_id, board=board, uci_move=result["uci"], source=result["source"],
        ),
    )


async def _bearer_user(request: Request, db: AsyncSession) -> User:
    """The user by the Authorization header or 401 - for saved personalities."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    user = await deps.user_from_token(db, token) if scheme.lower() == "bearer" and token else None
    if user is None:
        raise ApiError(401, "login_required_for_personality")
    return user


async def _ladder_game_for_save(
        user: User, payload: BotGameSaveRequest,
) -> tuple[ladder_service.LadderSession, int, ladder_service.Rung]:
    """The open ladder game that the game being saved corresponds to, or 409."""
    session = await ladder_service.get_session(user.id)
    found = ladder_service.find_rung(session.rung_key) if session else None
    if session is None or found is None:
        raise ApiError(409, "ladder_game_missing")
    _, rung = found
    expected = (rung.key, None) if rung.kind == "historical" else (CUSTOM_BOT_ID, rung.key)
    actual = (payload.bot_id, payload.personality_name if payload.bot_id == CUSTOM_BOT_ID else None)
    if actual != expected or payload.player_color != session.color:
        raise ApiError(409, "ladder_game_mismatch")
    return session, *found


async def _tournament_game_for_save(
        db: AsyncSession, user: User, payload: BotGameSaveRequest,
) -> tournament_service.PlayerGame:
    """The player's tournament game that the game being saved corresponds to: opponent, colour and time control - as in the
    tournament."""
    assert payload.tournament_game_id is not None
    try:
        played = await tournament_service.player_game(db, user, payload.tournament_game_id)
    except DomainError as exc:
        raise exc.to_http(404 if exc.code == "tournament_not_found" else 409) from None
    matches = (
        payload.player_color == played.color
        and tournament_service.opponent_matches(played.opponent, payload.bot_id, payload.personality_name)
        and (payload.base_time_ms, payload.increment_ms) == (played.game.base_time_ms, played.game.increment_ms)
        and not payload.start_fen
        and not payload.ladder
    )
    if not matches:
        raise ApiError(409, "tournament_game_mismatch")
    session = await ladder_service.get_session(user.id, "tournament")
    if session is None or session.tournament_game_id != played.game.id:
        # A tournament game is started via POST /tournaments/{id}/games/{game_id}/start (task A.2).
        raise ApiError(409, "tournament_game_not_started")
    return played


async def _resolve_personality_for_save(
        db: AsyncSession, user: User, payload: BotGameSaveRequest,
) -> tuple[str | None, int | None]:
    """(personality name, its target rating) for a game with the 'custom' bot; for historical ones - (None, None)."""
    if payload.bot_id != CUSTOM_BOT_ID:
        return None, None
    if payload.personality_id is not None:
        personality = await get_owned_personality(db, user.id, payload.personality_id)
        return personality.name, personality_config(personality).target_elo
    if payload.personality_name is None:
        raise ApiError(400, "custom_opponent_missing")
    # A workshop archetype (including a ladder opponent) - by the key "archetype:<id>": in the archive its name
    # will be shown in the player's language.
    archetype = ARCHETYPES_BY_KEY.get(payload.personality_name)
    if archetype is not None:
        return archetype.key, archetype.config.target_elo
    # A master of the past ("Time Machine") - under the PGN name ("Surname, Name"): the player name rules do not
    # apply to it (a comma and a space are forbidden in them - such a name cannot be taken by a personality), the strength is
    # from the registry.
    guest = GUESTS_BY_PGN_NAME.get(payload.personality_name)
    if guest is not None:
        return guest.pgn_name, guest.rating
    try:
        return validate_personality_name(payload.personality_name), None
    except PydanticCustomError as exc:
        raise ApiError(400, exc.type, **(exc.context or {})) from None


async def _remember_bot_game(db: AsyncSession, payload: BotGameSaveRequest, result: str, player_rating: int,
                             player_id: int) -> None:
    """
    The historical bot's memory after a game (src/services/bots/memory.py): the outcome of the opening book moves played -
    always; the memory of this opponent - if the player did not use the mentor; the bot's rating from games with humans -
    if additionally the game is not blindfold. A failure here is only written to the log.
    """
    bot_color = chess.BLACK if payload.player_color == "white" else chess.WHITE
    book = BOT_INSTANCES[payload.bot_id].opening_book
    try:
        await bot_memory.record_book(db, payload.bot_id, book, payload.moves_uci, bot_color, result)
        # The memory of the opponent (32.2): from a finished game without help - how the player really plays.
        if not payload.assisted and payload.moves_uci:
            await bot_memory.record_rival(db, payload.bot_id, player_id, book, payload.moves_uci, bot_color, result)
        if not payload.assisted and not payload.blindfold and payload.moves_uci:
            await bot_memory.record_rating(
                db, payload.bot_id, int(str(BOT_METADATA[payload.bot_id]["rating"])), player_rating,
                bot_memory.bot_points(result, bot_color))
    except Exception as exc:  # memory is not the main thing: the game is already in the archive
        await db.rollback()
        logger.warning("Bot memory update failed for %s: %s", payload.bot_id, exc)


@router.post("/save-game", response_model=BotGameSaveResponse)
async def save_bot_game(
        payload: BotGameSaveRequest,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    Saves a finished game against a historical bot or a personality from the workshop. Only for logged-in users.

    What it does: replays the submitted moves and determines the result itself (resolve_bot_game_outcome), writes the game to
    games (without rating, except a tournament one), for a ladder game updates the rating and the ladder rung, for a tournament
    game - records the result in the tournament, changes the player's rating and queues the bot games that have opened up,
    updates
    the historical bot's memory and queues a background review. A ladder or tournament game must match the one opened
    on the server (opponent, colour, time control) - otherwise 409; a hint or a takeback in a tournament game gives
    a loss, not the board result.
    """
    if payload.blindfold and (payload.ladder or payload.tournament_game_id):
        # Blindfold play is training: it does not exist in the ladder and the tournament (task 19.5).
        raise ApiError(400, "blindfold_not_allowed")
    if payload.bot_id != CUSTOM_BOT_ID and payload.bot_id not in BOT_METADATA:
        raise ApiError(404, "bot_not_found", bot_id=payload.bot_id)
    personality_name, personality_elo = await _resolve_personality_for_save(db, current_user, payload)
    ladder_game = await _ladder_game_for_save(current_user, payload) if payload.ladder else None
    tournament_game = await _tournament_game_for_save(db, current_user, payload) if payload.tournament_game_id else None

    if payload.player_color not in ("white", "black"):
        raise ApiError(400, "invalid_player_color")

    if payload.result not in ("1-0", "0-1", "1/2-1/2"):
        raise ApiError(400, "invalid_result")

    # A game without moves is not written to the archive - except counted ones (ladder, tournament) resigned or lost on
    # time before the first move: otherwise the tournament game would stay open, and the round unclosed.
    counted = ladder_game is not None or tournament_game is not None
    if counted and payload.termination == "agreement":
        # The server does not remember the bot's agreement to a draw - in a counted game it cannot be forged.
        raise ApiError(400, "termination_required")
    if not payload.moves_uci and not (counted and payload.termination in ("resignation", "timeout")):
        raise ApiError(400, "empty_moves")

    try:
        final_board = _replay_moves(payload.moves_uci, payload.start_fen)
        result, termination = resolve_bot_game_outcome(final_board, payload)
    except DomainValueError as exc:
        raise exc.to_http(400) from exc
    # The standard setup submitted as FEN is not a "custom position".
    start_fen = None if is_standard_start(final_board) else final_board.root().fen()
    payload = payload.model_copy(update={"result": result, "termination": termination, "start_fen": start_fen})

    bot_user = await _get_or_create_bot_user(db, payload.bot_id)

    if payload.player_color == "white":
        white_user, black_user = current_user, bot_user
    else:
        white_user, black_user = bot_user, current_user

    category = classify_time_control(payload.base_time_ms, payload.increment_ms)

    def _pgn_player(user: User) -> tuple[str, int]:
        if user.id == bot_user.id:
            # A personality opponent - under its own name (an archetype - under its English name) and with the target strength.
            if personality_name:
                archetype = ARCHETYPES_BY_KEY.get(personality_name)
                name = archetype.pgn_name if archetype else personality_name
                return name, personality_elo or user.rating_for(category)
            # A historical bot - under the PGN name, like masters' games in the archive.
            return str(BOT_METADATA[payload.bot_id]["pgn_name"]), user.rating_for(category)
        return user.username, user.rating_for(category)

    (white_name, white_elo), (black_name, black_elo) = _pgn_player(white_user), _pgn_player(black_user)
    try:
        pgn_text, final_fen = _build_pgn_string(
            moves_uci=payload.moves_uci,
            white_name=white_name,
            white_elo=white_elo,
            black_name=black_name,
            black_elo=black_elo,
            result=payload.result,
            start_fen=payload.start_fen,
        )
    except DomainValueError as exc:
        raise exc.to_http(400) from exc

    game_kwargs = _prepare_game_kwargs(
        white_id=white_user.id,
        black_id=black_user.id,
        pgn_text=pgn_text,
        final_fen=final_fen,
        payload=payload,
    )

    new_game = Game(**game_kwargs, personality_name=personality_name, assisted=payload.assisted,
                    blindfold_level=payload.blindfold, blindfold_peeks=payload.peeks if payload.blindfold else None)
    db.add(new_game)
    ladder_outcome = None
    if ladder_game is not None:
        session, rung_index, rung = ladder_game
        player_score = {"1-0": 1.0, "0-1": 0.0}.get(result, 0.5)
        if payload.player_color == "black" and result != "1/2-1/2":
            player_score = 1.0 - player_score
        ladder_outcome = await ladder_service.apply_result(db, current_user, rung, player_score, session.assisted)
    await product_metrics.record_event(db, current_user.id, product_metrics.GAME_FINISHED)
    await db.commit()
    await db.refresh(new_game)
    if ladder_game is not None:
        await ladder_service.clear_session(current_user.id)
    tournament_forfeit = None
    rating_change = None
    if tournament_game is not None:
        # An engine hint, analysis, takeback or mentor during a tournament game is a loss (task A.2):
        # an "uncounted" game cannot exist in a tournament.
        tournament_session = await ladder_service.get_session(current_user.id, "tournament")
        tournament_forfeit = (
            (tournament_session.assisted if tournament_session else None) or ("coach" if payload.assisted else None)
        )
        tournament_result = tournament_service.loss_for(payload.player_color) if tournament_forfeit else result
        await ladder_service.clear_session(current_user.id, "tournament")
        # The result goes to the tournament; the bot games opened by it are counted by the worker.
        # All tournaments are rated (owner's decision): the player's rating - by the game result in the tournament.
        rating_change = tournament_service.apply_rating(current_user, tournament_game, tournament_result)
        new_game.is_rated = True
        if tournament_game.color == "white":
            new_game.white_initial_rating, new_game.white_rating_delta = rating_change.before, rating_change.delta
        else:
            new_game.black_initial_rating, new_game.black_rating_delta = rating_change.before, rating_change.delta
        await tournament_service.record_result(
            db, tournament_game.tournament, tournament_game.game, tournament_result, new_game.id,
        )
        await db.refresh(tournament_game.tournament)
        schedule_tournament_simulations_in_background(
            await tournament_service.mark_for_queue(db, tournament_game.tournament)
        )
    # The bot's experience (task 32.1): opening lines - from any game from the initial position; rating - without help,
    # blindfold games and custom positions. A memory failure does not break the game: it is already saved.
    if payload.bot_id in BOT_INSTANCES and not personality_name and start_fen is None:
        await _remember_bot_game(db, payload, result,
                                 rating_change.before if rating_change else current_user.rating_for(category),
                                 current_user.id)
    # Background review: the game result is ready in advance, and personal puzzles are made from the player's mistakes (task
    # 13.5).
    schedule_game_analysis_in_background(new_game.id)

    return BotGameSaveResponse(
        game_id=new_game.id,
        status="finished",
        result=result,
        ladder=ladder_outcome,
        tournament_id=tournament_game.tournament.id if tournament_game else None,
        tournament_forfeit=tournament_forfeit,
        rating_before=rating_change.before if rating_change else None,
        rating_after=rating_change.after if rating_change else None,
        rating_delta=rating_change.delta if rating_change else None,
    )
