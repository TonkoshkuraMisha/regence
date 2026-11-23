# --- FILE: src/services/game_import.py ---
"""
Import of a player's games from lichess and chess.com (task 24.1): by username through the open APIs of both platforms or by
pasting PGN.
A reason to come to the site without abandoning the familiar platform: recent games go into the analysis with the mentor and
into the personal
puzzles "My mistakes" (13.5).

* Only open APIs without sign-in: we neither store nor ask for anyone's tokens. Only the username the player entered
  themselves goes to
  a third-party site; the client introduces itself with a generic name (ATTRIBUTION, "External services").
* Politeness to foreign APIs: per process -- one request to each site at a time; a 429 response puts the site on pause
  (SOURCE_COOLDOWN_S) for everyone, and the player gets the code import_source_busy. The import rate per player is limited by
  the
  API (RATE_LIMIT_GAME_IMPORT per RATE_LIMIT_GAME_IMPORT_WINDOW_S).
* Only ordinary chess (from any starting position); variants are skipped. The PGN is saved without comments,
  clocks and evaluations of a foreign engine -- we do the analysis ourselves.
* Games are stored separately from the site's games (models/imported_game.py): they do not affect rating, archive or
  statistics.
* A repeat import does not duplicate: uniqueness by (player, site, game id); for a pasted PGN the id is the SHA-1 of names,
  date, starting position and moves (_moves_digest).

Data: the imported_games table (+ personal_puzzles on deletion), the Redis key game_import:cooldown:<site>, the settings
GAME_IMPORT_* and RATE_LIMIT_GAME_IMPORT* (src/core/config.py). Called by src/api/game_import.py and the task
analyze_imported_game_task (src/worker/tasks.py). Errors are GameImportError with import_* codes (src/core/errors.py).
"""

import asyncio
import datetime as dt
import hashlib
import io
import json
import logging
import re
import time

import chess
import chess.pgn
import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.errors import DomainError
from src.db import redis as redis_module
from src.models.imported_game import ImportedGame
from src.models.puzzle import PersonalPuzzle
from src.models.user import User
from src.services.analysis_service import evaluate_pgn, is_current_analysis
from src.services.game_engine import normalize_result

logger = logging.getLogger(__name__)

# Supported sites; a pasted PGN is stored with the source "pgn".
SOURCES = ("lichess", "chesscom")
# Timeout of a request to a third-party API, seconds.
TIMEOUT_S = 15.0
# Client name for third-party APIs: generic, with no personal data.
USER_AGENT = "regence-game-import"
# Site pause after a 429 response, seconds (shared by all players via Redis).
SOURCE_COOLDOWN_S = 60
# How many monthly chess.com archives to look back through in search of N games.
CHESSCOM_MAX_ARCHIVES = 3
# Limit on the size of a pasted PGN, characters.
MAX_PGN_CHARS = 500_000
# Limit on the length of the player name in the record.
NAME_MAX = 60
# A valid username on a third-party site: checked before substitution into the request address.
USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{2,30}$")
# Game speeds that are stored (like the lichess time control categories).
SPEEDS = ("bullet", "blitz", "rapid", "classical", "daily")
# Loaded from the site: (game id, game, speed or None).
Fetched = list[tuple[str, chess.pgn.Game, str | None]]
# Ready to save: the same + the player's side ("white" / "black").
ToSave = list[tuple[str, chess.pgn.Game, str | None, str]]
# Values of the Variant header that count as ordinary chess.
_STANDARD_VARIANTS = {"", "standard", "from position", "fromposition"}

# Windows line breaks (including doubled "\r\r\n"), normalised to "\n".
_LINE_BREAKS = re.compile(r"\r+\n?")
# One lock per site: no more than one request to a site runs in a process.
_source_locks: dict[str, asyncio.Lock] = {}


class GameImportError(DomainError):
    """An import refusal with a code and an HTTP status."""

    def __init__(self, code: str, status_code: int = 400, **params):
        super().__init__(code, **params)
        self.status_code = status_code


# --- PGN parsing --------------------------------------------------------------------------------------------------


def speed_from_time_control(value: str | None) -> str | None:
    """The speed by the TimeControl header ("180+2", "-", "1/86400"): as in lichess -- base + 40 x increment."""
    if not value or value == "?":
        return None
    if value == "-" or "/" in value:
        return "daily"
    base, _, increment = value.partition("+")
    try:
        estimate = int(base) + 40 * int(increment or 0)
    except ValueError:
        return None
    if estimate < 180:
        return "bullet"
    if estimate < 480:
        return "blitz"
    if estimate < 1500:
        return "rapid"
    return "classical"


def _rating(value: str | None) -> int | None:
    """A rating from a PGN header: an integer from 1 to 3999, otherwise None."""
    try:
        rating = int(value or "")
    except ValueError:
        return None
    return rating if 0 < rating < 4000 else None


def _played_at(headers: chess.pgn.Headers) -> dt.datetime | None:
    """The game time (UTC) from UTCDate/UTCTime or Date; missing or unparsable -- None."""
    date = headers.get("UTCDate") or headers.get("Date") or ""
    clock = headers.get("UTCTime") or "00:00:00"
    try:
        return dt.datetime.strptime(f"{date} {clock}","%Y.%m.%d %H:%M:%S").replace(tzinfo=dt.UTC)
    except ValueError:
        return None


def _clean_pgn(game: chess.pgn.Game) -> str:
    """A PGN without comments (clocks, foreign engine evaluations) and variations -- only headers and moves."""
    exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=False)
    return game.accept(exporter)


def _moves_digest(game: chess.pgn.Game) -> str:
    """The SHA-1 of names, date, starting position and moves: the id of a game that has no id on the site."""
    headers = game.headers
    key = "|".join([headers.get("White", ""), headers.get("Black", ""), headers.get("Date", ""),
                    headers.get("FEN", ""), " ".join(move.uci() for move in game.mainline_moves())])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def read_games(pgn_text: str, limit: int) -> list[chess.pgn.Game]:
    """Games from a PGN document (no more than limit): only ordinary chess, without parse errors and with at least one move."""
    # Several games in a row: blank lines between them are significant, so not normalize_pgn_text (it is for one
    # game); only Windows line breaks ("\r\r\n" -> one line) and the BOM.
    stream = io.StringIO(_LINE_BREAKS.sub("\n", pgn_text.lstrip("\ufeff")))
    games: list[chess.pgn.Game] = []
    # Broken and empty games are skipped, but their number is limited too -- long junk is not parsed to the end.
    for _ in range(limit * 5):
        if len(games) >= limit:
            break
        try:
            game = chess.pgn.read_game(stream)
        except (ValueError, KeyError):
            continue
        if game is None:
            break
        variant = game.headers.get("Variant", "").strip().lower()
        if variant not in _STANDARD_VARIANTS or game.errors or game.next() is None:
            continue
        games.append(game)
    return games


def _color_of(game: chess.pgn.Game, player: str) -> str | None:
    """The player's side by name in the White/Black headers (case-insensitive); None -- did not play in the game."""
    wanted = player.strip().lower()
    if not wanted:
        return None
    if game.headers.get("White", "").strip().lower() == wanted:
        return "white"
    if game.headers.get("Black", "").strip().lower() == wanted:
        return "black"
    return None


def _record(user: User, source: str, external_id: str, game: chess.pgn.Game, color: str,
            speed: str | None = None) -> ImportedGame:
    """An ImportedGame record from a PGN game; the speed -- the passed one or from TimeControl."""
    headers = game.headers
    return ImportedGame(
        user_id=user.id, source=source, external_id=external_id[:64], color=color,
        white_name=headers.get("White", "?")[:NAME_MAX], black_name=headers.get("Black", "?")[:NAME_MAX],
        white_rating=_rating(headers.get("WhiteElo")), black_rating=_rating(headers.get("BlackElo")),
        result=normalize_result(headers.get("Result")), speed=speed or speed_from_time_control(headers.get("TimeControl")),
        played_at=_played_at(headers), pgn=_clean_pgn(game),
    )


# --- third-party sites -------------------------------------------------------------------------------------------


def _cooldown_key(source: str) -> str:
    """The Redis key of a site pause."""
    return f"game_import:cooldown:{source}"


async def _ensure_source_available(source: str) -> None:
    """The site is paused after a 429: the key holds until when (unix), to tell the player how long to wait."""
    try:
        until = float(await redis_module.redis_client.get(_cooldown_key(source)) or 0)
    except Exception as exc:
        logger.warning("Redis unavailable for import cooldown: %s", exc)
        return
    left = int(until - time.time())
    if left > 0:
        raise GameImportError("import_source_busy", 503, retry_after=left)


async def _pause_source(source: str) -> None:
    """Puts the site on pause for SOURCE_COOLDOWN_S; an unavailable Redis is only written to the log."""
    try:
        await redis_module.redis_client.set(_cooldown_key(source), str(time.time() + SOURCE_COOLDOWN_S),
                                            ex=SOURCE_COOLDOWN_S)
    except Exception as exc:
        logger.warning("Redis unavailable for import cooldown: %s", exc)


async def _get(client: httpx.AsyncClient, source: str, url: str, **kwargs) -> httpx.Response:
    """GET to a third-party API: a network error and statuses other than 200 become import_* codes; a 429 sets the pause."""
    try:
        response = await client.get(url, **kwargs)
    except httpx.HTTPError as exc:
        logger.warning("Import request to %s failed: %s", source, exc)
        raise GameImportError("import_source_unavailable", 502) from None
    if response.status_code == 404:
        raise GameImportError("import_player_not_found", 404)
    if response.status_code == 429:
        await _pause_source(source)
        raise GameImportError("import_source_busy", 503, retry_after=SOURCE_COOLDOWN_S)
    if response.status_code != 200:
        logger.warning("Import request to %s returned %s", source, response.status_code)
        raise GameImportError("import_source_unavailable", 502)
    return response


async def _fetch_lichess(client: httpx.AsyncClient, username: str, limit: int) -> Fetched:
    """Recent games from lichess in one PGN request; the id from the Site link, the speed from the Event header."""
    base = settings.GAME_IMPORT_LICHESS_URL.rstrip("/")
    response = await _get(client, "lichess", f"{base}/api/games/user/{username}", params={
        "max": limit, "perfType": "ultraBullet,bullet,blitz,rapid,classical,correspondence",
        "finished": "true", "ongoing": "false", "clocks": "false", "evals": "false", "opening": "true",
    }, headers={"Accept": "application/x-chess-pgn"})
    result = []
    for game in read_games(response.text, limit):
        site = game.headers.get("Site", "")
        external_id = site.rstrip("/").rsplit("/", 1)[-1] if site.startswith("http") else _moves_digest(game)
        event = game.headers.get("Event", "").lower()
        speed = next((name for name in SPEEDS if name in event), None)
        if speed is None and "correspondence" in event:
            speed = "daily"
        result.append((external_id, game, speed))
    return result


async def _fetch_chesscom(client: httpx.AsyncClient, username: str, limit: int) -> Fetched:
    """chess.com games from the last CHESSCOM_MAX_ARCHIVES monthly archives, from newest to oldest."""
    base = settings.GAME_IMPORT_CHESSCOM_URL.rstrip("/")
    response = await _get(client, "chesscom", f"{base}/pub/player/{username.lower()}/games/archives")
    try:
        archives = [url for url in response.json().get("archives", []) if isinstance(url, str)]
    except ValueError:
        raise GameImportError("import_source_unavailable", 502) from None
    result: Fetched = []
    for archive_url in reversed(archives[-CHESSCOM_MAX_ARCHIVES:]):
        # We follow only addresses of the same API: a link from the response does not lead the request to an arbitrary host.
        if not archive_url.startswith(f"{base}/pub/player/"):
            continue
        try:
            items = (await _get(client, "chesscom", archive_url)).json().get("games", [])
        except ValueError:
            raise GameImportError("import_source_unavailable", 502) from None
        for item in reversed(items):
            if len(result) >= limit:
                return result
            if not isinstance(item, dict) or item.get("rules") != "chess" or not item.get("pgn"):
                continue
            games = read_games(str(item["pgn"]), 1)
            if not games:
                continue
            external_id = str(item.get("uuid") or str(item.get("url", "")).rstrip("/").rsplit("/", 1)[-1]
                              or _moves_digest(games[0]))
            speed = item.get("time_class") if item.get("time_class") in SPEEDS else None
            result.append((external_id, games[0], speed))
    return result


async def fetch_games(source: str, username: str, limit: int) -> Fetched:
    """A player's recent finished games on a site: (game id, game, speed), from newest to oldest."""
    if source not in SOURCES:
        raise GameImportError("import_source_unknown")
    if not USERNAME_RE.match(username):
        raise GameImportError("import_username_invalid")
    await _ensure_source_available(source)
    lock = _source_locks.setdefault(source, asyncio.Lock())
    async with lock, httpx.AsyncClient(timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT},
                                       follow_redirects=False) as client:
        if source == "lichess":
            return await _fetch_lichess(client, username, limit)
        return await _fetch_chesscom(client, username, limit)


# --- saving ------------------------------------------------------------------------------------------------------


async def _room_left(db: AsyncSession, user: User) -> int:
    """How many games the player can still save before the GAME_IMPORT_MAX_STORED limit."""
    stored = await db.scalar(select(func.count()).select_from(ImportedGame).where(ImportedGame.user_id == user.id)) or 0
    return max(0, settings.GAME_IMPORT_MAX_STORED - stored)


async def _save(db: AsyncSession, user: User, source: str,
                items: ToSave) -> dict:
    """
    items: (game id, game, speed, player's side). Repeats are skipped, new ones are saved, but no more than the room up to the
    storage limit (no room at all -- import_limit_reached). Returns {"added": [record ids], "duplicates"}.
    """
    room = await _room_left(db, user)
    if room <= 0:
        raise GameImportError("import_limit_reached", 409, max=settings.GAME_IMPORT_MAX_STORED)
    ids = [external_id[:64] for external_id, *_ in items]
    known = set((await db.scalars(select(ImportedGame.external_id).where(
        ImportedGame.user_id == user.id, ImportedGame.source == source, ImportedGame.external_id.in_(ids),
    ))).all()) if ids else set()
    added: list[ImportedGame] = []
    duplicates = 0
    for external_id, game, speed, color in items:
        key = external_id[:64]
        if key in known:
            duplicates += 1
            continue
        if len(added) >= room:
            break
        known.add(key)
        record = _record(user, source, key, game, color, speed)
        db.add(record)
        added.append(record)
    await db.commit()
    return {"added": [record.id for record in added], "duplicates": duplicates}


async def import_from_site(db: AsyncSession, user: User, source: str, username: str, limit: int) -> dict:
    """
    Import of a player's recent games from lichess or chess.com by username. Games in which this username did not play are
    skipped;
    those already loaded count as duplicates.
    """
    fetched = await fetch_games(source, username, limit)
    items: ToSave = []
    skipped = 0
    for external_id, game, speed in fetched:
        color = _color_of(game, username)
        if color is None:
            skipped += 1
            continue
        items.append((external_id, game, speed, color))
    if not items:
        return {"added": [], "duplicates": 0, "skipped": skipped}
    saved = await _save(db, user, source, items)
    return {**saved, "skipped": skipped}


async def import_pgn(db: AsyncSession, user: User, pgn_text: str, player: str, limit: int) -> dict:
    """A pasted PGN: the player's side -- by name in the White/Black headers (by default the site username)."""
    if len(pgn_text) > MAX_PGN_CHARS:
        raise GameImportError("import_pgn_too_large", max_kb=MAX_PGN_CHARS // 1000)
    games = read_games(pgn_text, limit)
    if not games:
        raise GameImportError("import_pgn_empty")
    name = player.strip() or user.username
    items: ToSave = []
    skipped = 0
    for game in games:
        color = _color_of(game, name)
        if color is None:
            skipped += 1
            continue
        items.append((_moves_digest(game), game, None, color))
    if not items:
        raise GameImportError("import_player_not_in_pgn", player=name)
    saved = await _save(db, user, "pgn", items)
    return {**saved, "skipped": skipped}


# --- viewing, analysis, deletion -----------------------------------------------------------------------------------


def _aware(value: dt.datetime | None) -> str | None:
    """Time in ISO 8601; a value without a time zone counts as UTC."""
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=dt.UTC)).isoformat()


def view(game: ImportedGame, puzzles: int = 0) -> dict:
    """An import list row (without PGN); puzzles -- the number of personal puzzles made from this game."""
    return {
        "id": game.id, "source": game.source, "color": game.color,
        "white": game.white_name, "black": game.black_name,
        "white_rating": game.white_rating, "black_rating": game.black_rating,
        "result": game.result, "speed": game.speed, "played_at": _aware(game.played_at),
        "analyzed": bool(game.analysis_json), "puzzles": puzzles,
    }


async def get_own(db: AsyncSession, user: User, imported_id: int) -> ImportedGame:
    """
    The player's own imported game; someone else's or non-existent -- imported_game_not_found (404, without revealing someone
    else's).
    """
    game = await db.get(ImportedGame, imported_id)
    if game is None or game.user_id != user.id:
        raise GameImportError("imported_game_not_found", 404)
    return game


async def list_games(db: AsyncSession, user: User, offset: int, limit: int) -> dict:
    """
    Imported games of a player (newest first) with the number of personal puzzles made from each, and the storage limit.
    """
    total = await db.scalar(select(func.count()).select_from(ImportedGame).where(ImportedGame.user_id == user.id)) or 0
    games = (await db.scalars(
        select(ImportedGame).where(ImportedGame.user_id == user.id)
        .order_by(ImportedGame.played_at.desc().nulls_last(), ImportedGame.id.desc()).offset(offset).limit(limit)
    )).all()
    counts: dict[int | None, int] = {}
    if games:
        rows = await db.execute(
            select(PersonalPuzzle.imported_game_id, func.count()).where(
                PersonalPuzzle.imported_game_id.in_([game.id for game in games])
            ).group_by(PersonalPuzzle.imported_game_id)
        )
        counts = {imported_id: count for imported_id, count in rows.all()}
    return {"total": total, "max": settings.GAME_IMPORT_MAX_STORED,
            "games": [view(game, counts.get(game.id, 0)) for game in games]}


async def remove(db: AsyncSession, user: User, imported_id: int) -> None:
    """Deletes the player's own imported game together with the personal puzzles made from it."""
    game = await get_own(db, user, imported_id)
    await db.execute(delete(PersonalPuzzle).where(PersonalPuzzle.imported_game_id == game.id))
    await db.delete(game)
    await db.commit()


def cached_analysis(game: ImportedGame) -> dict | None:
    """The saved analysis, if it exists, is readable and matches the current PGN and the analysis version; otherwise None."""
    if not game.analysis_json:
        return None
    try:
        data = json.loads(game.analysis_json)
    except ValueError:
        return None
    return data if is_current_analysis(data, game.pgn) else None


async def analyze(db: AsyncSession, game: ImportedGame, force: bool = False) -> dict:
    """The full analysis of a game (the same as for site games); cached in analysis_json."""
    if not force:
        cached = cached_analysis(game)
        if cached is not None:
            return cached
    report = await evaluate_pgn(game.pgn)
    game.analysis_json = json.dumps(report, ensure_ascii=False)
    await db.commit()
    return report
