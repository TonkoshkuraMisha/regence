# --- FILE: src/services/bots/memory.py ---
"""
Bot memory (task 32.1). A bot stays itself — in its own style and near its declared strength — but remembers what has been
played.

* Openings. For each game played (with humans — save-game, and in bot tournaments — simulation) the result is recorded for the
  bot at each of its book moves while the game has not left the book (no further than BOOK_PLIES half-moves). When choosing a
  move the
  book weight is multiplied by book_factor: the smoothed result (PRIOR virtual games at 50 %) is turned into a
  multiplier from FACTOR_MIN to FACTOR_MAX. The choice is only among moves of its historical book: the bot does not
  invent new variations, it simply plays the lost ones less often.
* Strength. The bot's rating is recalculated from games with humans like a player's (Elo, coefficient K) — without games with
  help,
  blindfold and from a given position. The initial value is the calibration (calibration.json) or the declared strength. If
  after
  OFFSET_MIN_GAMES games the gap from the declared strength is at least DRIFT, once every OFFSET_EVERY games the correction to
  the bot's UCI_Elo
  is shifted by a quarter of the gap (no further than MAX_OFFSET): the bot returns to the declared strength, and the
  declared strength is not fitted to the bot — rated games against it stay fair.

Memory is read from the database into the process cache (refresh, no more than once per REFRESH_SECONDS per bot): move
selection is synchronous and
does not touch the database. Tables (src/models/bot_memory.py): bot_opening_stats, bot_ratings, bot_rivals, bot_rival_stats.
Results are written by src/api/bots.py (games with humans), tournament simulation and the analyze_game task (opponent errors);
it is read by move selection (base.HistoricalBot._book_move and _candidate_scores).

* Opponent (task 32.2). From finished games with a human the bot remembers the result of each of its book moves against this
  very player. With a regular opponent (at least RIVAL_MIN_GAMES games) the move weight is additionally multiplied by
  rival_factor from RIVAL_MIN to RIVAL_MAX: variations where the player scored less are played more often (it is harder for him
  there), where the bot
  lost — less often; the move with which the bot lost to this player last time — another x LAST_LOSS. The opponent memory
  is loaded on a move request (load_rival) and passed to the synchronous move selection through contextvars: the bot objects
  are shared across all requests.
* Where the opponent errs (32.2, from the analysis). When the background game analysis is ready (games.analysis_json, task
  analyze_game), record_rival_errors marks the bot's book moves after which the player made a mistake or blunder within the
  next ERROR_WINDOW
  half-moves (the ERROR_CLASSES classes of the analysis). The weight of such a move against this player is another
  x up to ERROR_MAX by the share of games with an error: the bot more willingly steers into a position where he already erred.
  The same
  games are counted as for the opponent results: a historical bot, the standard setup, no coach.
"""

import json
import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass, field

import chess
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.bot_memory import BotOpeningStat, BotRating, BotRival, BotRivalStat
from src.models.game import Game, GameStatus
from src.models.user import User

logger = logging.getLogger(__name__)

# Smoothing of a book move's experience: this many "virtual" games with a 50 % result are added to the real ones.
PRIOR = 4
# Bounds of the book move weight multiplier by its results in the bot's games (0.5 — always lost, 1.5 — always won).
FACTOR_MIN, FACTOR_MAX = 0.5, 1.5
# Experience is recorded for book moves no further than this many half-moves from the start of the game.
BOOK_PLIES = 24
# Coefficient K of the bot's rating update by the Elo formula (as for a player).
K = 16
# The strength correction starts being computed after this many games with humans and is recalculated every OFFSET_EVERY games.
OFFSET_MIN_GAMES = 50
OFFSET_EVERY = 25
# Gap between the bot's rating and the declared strength (points) from which the correction shifts.
DRIFT = 100
# The largest correction to the bot's UCI_Elo (points in either direction).
MAX_OFFSET = 150
# How often (s) the process cache is re-read from the database for one bot.
REFRESH_SECONDS = 300
# Memory about a specific player applies from this many games with him.
RIVAL_MIN_GAMES = 2
# Bounds of the move weight multiplier by the bot's points against this player.
RIVAL_MIN, RIVAL_MAX = 0.25, 1.75
# Additional multiplier for the move with which the bot lost to this player last time.
LAST_LOSS = 0.1
# A player's error is credited to a book move if it happened no further than ERROR_WINDOW half-moves after it.
ERROR_WINDOW = 12
# Analysis move classes (analysis_service.classify_move_by_cp_loss) that count as a player's error.
ERROR_CLASSES = ("Mistake", "Blunder")
# The cap of the addition to a move's weight, after which the player erred in all games.
ERROR_MAX = 1.5
# Suffix of the bot's service name if its name is taken by a human (api/bots._get_or_create_bot_user).
BOT_USERNAME_SUFFIX = "_bot"

# Process cache. _book: bot → (position key, UCI) → (games, bot points); _offset: bot → UCI_Elo correction;
# _loaded_at: bot → the moment (time.monotonic) of the last read from the database.
_book: dict[str, dict[tuple[str, str], tuple[int, float]]] = {}
_offset: dict[str, int] = {}
_loaded_at: dict[str, float] = {}


@dataclass
class Rival:
    """A bot's memory about one player for the duration of a move request."""
    bot_id: str
    games: int
    # Book move (position key, UCI) → (games with it against the player, bot points, whether the bot lost with it last time).
    moves: dict[tuple[str, str], tuple[int, float, bool]] = field(default_factory=dict)
    # Book move → in how many games the player erred soon after it (from the analysis).
    errors: dict[tuple[str, str], int] = field(default_factory=dict)


_rival: ContextVar[Rival | None] = ContextVar("bot_rival", default=None)


def use_rival(rival: Rival | None) -> None:
    """The opponent of the current request (asyncio.to_thread copies the context into the move selection thread)."""
    _rival.set(rival)


def rival_factor(rival: Rival, fen_key: str, uci: str) -> float:
    """
    Book move weight multiplier against this player: from RIVAL_MIN to RIVAL_MAX by the bot's points with this move, plus an
    addition
    for the player's errors after it (up to ERROR_MAX), x LAST_LOSS if the bot lost with it last time. 1.0 — no experience.
    """
    games, points, last_lost = rival.moves.get((fen_key, uci), (0, 0.0, False))
    if games == 0:
        return 1.0
    rate = (points + 1.0) / (games + 2.0)
    factor = RIVAL_MIN + (RIVAL_MAX - RIVAL_MIN) * rate
    # Share of games where the player erred after this move; +1 in the denominator — one error is not yet a pattern.
    factor *= 1.0 + (ERROR_MAX - 1.0) * rival.errors.get((fen_key, uci), 0) / (games + 1)
    return factor * LAST_LOSS if last_lost else factor


def book_factor(bot_id: str, fen_key: str, uci: str) -> float:
    """Book move weight multiplier by the bot's experience and, if it plays a regular opponent, by the games with him."""
    factor = 1.0
    games, points = _book.get(bot_id, {}).get((fen_key, uci), (0, 0.0))
    if games:
        rate = (points + PRIOR * 0.5) / (games + PRIOR)
        factor = FACTOR_MIN + (FACTOR_MAX - FACTOR_MIN) * rate
    rival = _rival.get()
    if rival is not None and rival.bot_id == bot_id and rival.games >= RIVAL_MIN_GAMES:
        factor *= rival_factor(rival, fen_key, uci)
    return factor


def strength_offset(bot_id: str) -> int:
    """Correction to the bot's UCI_Elo (points) from the cache; 0 — no correction or memory not loaded yet."""
    return _offset.get(bot_id, 0)


def forget() -> None:
    """Clear the process cache (tests)."""
    _book.clear()
    _offset.clear()
    _loaded_at.clear()


async def refresh(db: AsyncSession, bot_id: str, *, force: bool = False) -> None:
    """Load the book experience and strength correction of the bot from the database into the cache; without force — no more
    than once per REFRESH_SECONDS."""
    if not force and time.monotonic() - _loaded_at.get(bot_id, -REFRESH_SECONDS) < REFRESH_SECONDS:
        return
    rows = (await db.execute(select(BotOpeningStat).where(BotOpeningStat.bot_id == bot_id))).scalars().all()
    _book[bot_id] = {(r.fen_key, r.uci): (r.games, r.points) for r in rows}
    rating = await db.get(BotRating, bot_id)
    _offset[bot_id] = rating.offset if rating else 0
    _loaded_at[bot_id] = time.monotonic()


def bot_points(result: str, bot_color: chess.Color) -> float:
    """Bot points by the result of a PGN game ("1-0", "0-1", "1/2-1/2"): 1, 0 or 0.5."""
    if result == "1/2-1/2":
        return 0.5
    white_won = result == "1-0"
    return 1.0 if white_won == (bot_color == chess.WHITE) else 0.0


def book_moves_played(opening_book: dict, moves_uci: list[str], bot_color: chess.Color) -> list[tuple[str, str]]:
    """The bot's moves from its book from the start of the game — up to the first exit from the book (by either side) or
    BOOK_PLIES."""
    return [(key, uci) for _, key, uci in book_plies(opening_book, moves_uci, bot_color)]


def book_plies(opening_book: dict, moves_uci: list[str], bot_color: chess.Color) -> list[tuple[int, str, str]]:
    """The same as book_moves_played, with the half-move number of each move (1 — the first move of the game, like ply in
    the analysis)."""
    from src.services.bots.base import normalize_fen_key

    board = chess.Board()
    played: list[tuple[int, str, str]] = []
    for index, uci in enumerate(moves_uci[:BOOK_PLIES]):
        key = normalize_fen_key(board)
        if board.turn == bot_color:
            known = {str(entry[0]) for entry in opening_book.get(key, [])}
            if uci not in known:
                break
            played.append((index + 1, key, uci))
        try:
            board.push_uci(uci)
        except ValueError:
            break
    return played


def erred_after(book: list[tuple[int, str, str]], report_moves: list[dict], player_color: str) -> set[tuple[str, str]]:
    """
    Book moves of the bot after which the player erred: in the analysis (moves from analysis_json) the player's move has a
    class from
    ERROR_CLASSES no further than ERROR_WINDOW half-moves after the bot's move.
    """
    error_plies = [int(item["ply"]) for item in report_moves
                   if item.get("color") == player_color and item.get("classification") in ERROR_CLASSES]
    return {(key, uci) for ply, key, uci in book
            if any(ply < error <= ply + ERROR_WINDOW for error in error_plies)}


async def record_book(db: AsyncSession, bot_id: str, opening_book: dict, moves_uci: list[str],
                      bot_color: chess.Color, result: str) -> int:
    """Record the game result for the bot's book moves; returns how many moves were counted. The commit is here."""
    played = book_moves_played(opening_book, moves_uci, bot_color)
    if not played:
        return 0
    points = bot_points(result, bot_color)
    for fen_key, uci in played:
        row = await db.scalar(select(BotOpeningStat).where(
            BotOpeningStat.bot_id == bot_id, BotOpeningStat.fen_key == fen_key, BotOpeningStat.uci == uci))
        if row is None:
            db.add(BotOpeningStat(bot_id=bot_id, fen_key=fen_key, uci=uci, games=1, points=points))
        else:
            row.games += 1
            row.points += points
    try:
        await db.commit()
    except IntegrityError:  # the same position was written by a parallel game — this game's experience is not critical
        await db.rollback()
        logger.info("Bot opening stat race for %s", bot_id)
        return 0
    _loaded_at.pop(bot_id, None)
    return len(played)


def expected(rating: float, opponent: float) -> float:
    """Expected result by the Elo formula for a player with the given rating against opponent."""
    return 1.0 / (1.0 + 10 ** ((opponent - rating) / 400))


def next_offset(offset: int, rating: float, declared: int) -> int:
    """Strength correction: a shift by a quarter of the gap if it is at least DRIFT; within MAX_OFFSET."""
    gap = declared - rating
    if abs(gap) < DRIFT:
        return offset
    return max(-MAX_OFFSET, min(MAX_OFFSET, offset + round(gap / 4)))


async def record_rating(db: AsyncSession, bot_id: str, declared: int, opponent_rating: int, score: float) -> BotRating:
    """A game with a human: the bot's Elo rating and, when due, a new strength correction. The commit is here."""
    from src.services.bots import calibration

    row = await db.get(BotRating, bot_id)
    if row is None:
        row = BotRating(bot_id=bot_id, rating=float(calibration.strength_of(bot_id, declared).rating), games=0,
                        offset=0, offset_games=0)
        db.add(row)
    row.rating = row.rating + K * (score - expected(row.rating, opponent_rating))
    row.games = (row.games or 0) + 1
    if row.games >= OFFSET_MIN_GAMES and row.games - (row.offset_games or 0) >= OFFSET_EVERY:
        offset = next_offset(row.offset or 0, row.rating, declared)
        if offset != row.offset:
            logger.info("Bot %s strength offset %s -> %s (rating %.0f, declared %s, games %s)",
                        bot_id, row.offset, offset, row.rating, declared, row.games)
        row.offset, row.offset_games = offset, row.games
    await db.commit()
    _offset[bot_id] = row.offset
    return row


async def live_strength(db: AsyncSession) -> dict[str, BotRating]:
    """Live rating and correction of all bots from bot_ratings: bot_id → row."""
    return {r.bot_id: r for r in (await db.execute(select(BotRating))).scalars().all()}

async def load_rival(db: AsyncSession, bot_id: str, user_id: int | None) -> Rival | None:
    """
    What the bot remembers about a player: how many games were played and how the moves played against him ended. None — the
    player did not
    sign in or there were no games with him yet.
    """
    if user_id is None:
        return None
    summary = await db.scalar(select(BotRival).where(BotRival.bot_id == bot_id, BotRival.user_id == user_id))
    if summary is None:
        return None
    rows = (await db.execute(select(BotRivalStat).where(
        BotRivalStat.bot_id == bot_id, BotRivalStat.user_id == user_id))).scalars().all()
    return Rival(bot_id, summary.games, {(r.fen_key, r.uci): (r.games, r.points, r.last_lost) for r in rows},
                 {(r.fen_key, r.uci): r.errors for r in rows if r.errors})


async def record_rival(db: AsyncSession, bot_id: str, user_id: int, opening_book: dict, moves_uci: list[str],
                       bot_color: chess.Color, result: str) -> None:
    """A finished game with a player: the result goes into the opponent summary and the bot's book moves against him. The
    commit is here."""
    points = bot_points(result, bot_color)
    summary = await db.scalar(select(BotRival).where(BotRival.bot_id == bot_id, BotRival.user_id == user_id))
    if summary is None:
        db.add(BotRival(bot_id=bot_id, user_id=user_id, games=1, points=points))
    else:
        summary.games += 1
        summary.points += points
    for fen_key, uci in book_moves_played(opening_book, moves_uci, bot_color):
        row = await db.scalar(select(BotRivalStat).where(
            BotRivalStat.bot_id == bot_id, BotRivalStat.user_id == user_id, BotRivalStat.fen_key == fen_key,
            BotRivalStat.uci == uci))
        if row is None:
            db.add(BotRivalStat(bot_id=bot_id, user_id=user_id, fen_key=fen_key, uci=uci, games=1, points=points,
                                last_lost=points == 0.0))
        else:
            row.games += 1
            row.points += points
            row.last_lost = points == 0.0
    try:
        await db.commit()
    except IntegrityError:  # a parallel game of the same player with the same bot — this one's experience is not critical
        await db.rollback()


async def rivals_of(db: AsyncSession, user_id: int) -> list[BotRival]:
    """Summaries for the bots the player has played: more games — higher."""
    return list((await db.execute(select(BotRival).where(BotRival.user_id == user_id)
                                  .order_by(BotRival.games.desc()))).scalars().all())


def _bot_id_of(user: User) -> str | None:
    """The historical bot behind a player's record (the name is the bot id, sometimes with a service suffix); otherwise
    None."""
    from src.services.bots import BOT_INSTANCES

    if not user.is_bot:
        return None
    name = user.username.removesuffix(BOT_USERNAME_SUFFIX)
    return name if name in BOT_INSTANCES else None


async def record_rival_errors(db: AsyncSession, game_id: int) -> int:
    """
    Player errors from a ready analysis of a game with a historical bot (called by the analyze_game task after the analysis):
    errors is added to the bot's book moves against this player. The game is the same one record_rival counts: finished,
    from the standard setup, without a coach, not a workshop persona. A repeated analysis does not double the count
    (BotRival.errors_game_id). Returns the number of marked book moves. The commit is here.
    """
    from src.services.bots import BOT_INSTANCES

    game = await db.get(Game, game_id)
    if (game is None or game.status != GameStatus.COMPLETED or not game.analysis_json or game.assisted
            or game.is_simulation or game.personality_name or "[FEN " in (game.pgn or "")):
        return 0
    white, black = await db.get(User, game.white_player_id), await db.get(User, game.black_player_id)
    if white is None or black is None:
        return 0
    bot_id, bot_color, player = _bot_id_of(white), chess.WHITE, black
    if bot_id is None:
        bot_id, bot_color, player = _bot_id_of(black), chess.BLACK, white
    if bot_id is None or player.is_bot:
        return 0
    summary = await db.scalar(select(BotRival).where(BotRival.bot_id == bot_id, BotRival.user_id == player.id))
    if summary is None or (summary.errors_game_id or 0) >= game.id:
        return 0
    report_moves = json.loads(game.analysis_json).get("moves", [])
    book = book_plies(BOT_INSTANCES[bot_id].opening_book, [str(m["uci"]) for m in report_moves], bot_color)
    marked = erred_after(book, report_moves, "black" if bot_color == chess.WHITE else "white")
    for fen_key, uci in marked:
        row = await db.scalar(select(BotRivalStat).where(
            BotRivalStat.bot_id == bot_id, BotRivalStat.user_id == player.id, BotRivalStat.fen_key == fen_key,
            BotRivalStat.uci == uci))
        if row is not None:
            row.errors += 1
    summary.errors_game_id = game.id
    await db.commit()
    return len(marked)
