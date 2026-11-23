# --- FILE: src/services/tournament_simulation.py ---
"""
Bot-vs-bot games in a tournament (task 15.2). They are computed in Celery, not in the API process: a tournament of 8
participants is 28 games. The search depth and time are lowered, the game length is limited: a game unfinished by
SIM_MAX_PLIES is decided by the engine evaluation (static - without the engine).

Strength in the simulation (task 28.2). An ordinary bot move limits strength with a reference Stockfish move with UCI_Elo,
but that needs time: at 0.1 s per move the rating stopped meaning anything (measurement of 17.11: 2400 against 1600 - 3.5
of 8, 2200 against 1700 - 4.5 of 8), and at full time a game takes over a minute - a tournament of 23 participants cannot
be played that way. Therefore the simulation has its own model (SimulatedPlayer): the best moves are evaluated at full
strength, and the participant chooses among them randomly, with a weight that falls with the loss in evaluation; the lower
the rating, the slower it falls (temperature_cp). The opening book and the participant's style are kept.

Each game is saved with a real PGN, without a rating, with the is_simulation mark: it does not enter Live,
the archive and profile statistics and is opened in GameViewer by a link from the tournament. One tournament game is taken
by one worker (tournament_games.started_at); if the worker crashed in the middle of a game, after CLAIM_TIMEOUT it can be
taken again.

Data: the tables tournament_games, tournament_players, games; the historical bots' opening experience - bots/memory.py;
tuning of archetypes - bots/selfplay.py; Stockfish - only through the engine pool (engine_work "simulation").
simulate() is run by the Celery task simulate_tournament_game (src/worker/tasks.py); games are queued by
tournaments.mark_for_queue. play_game and the SIM_* limits are also used by bot self-play (bots/selfplay.py).
"""

import asyncio
import logging
import math
import random
from collections.abc import Callable
from datetime import UTC, datetime

import chess
from sqlalchemy import or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.game import Game, GameStatus
from src.models.tournament import Tournament, TournamentGame, TournamentPlayer
from src.services import tournaments
from src.services.bots import memory as bot_memory
from src.services.bots import selfplay
from src.services.bots.base import (
    HistoricalBot,
    analyse_with_stockfish,
    fallback_scores,
    resolve_stockfish_path,
    static_board_eval_cp,
)
from src.services.engine_pool import engine_work

logger = logging.getLogger(__name__)

# Limit of game length in plies: beyond it adjudicate decides the game.
SIM_MAX_PLIES = 200
# Ceilings of search depth and time (seconds) of a bot in the simulation: they speed up the game at the cost of move quality.
SIM_MAX_DEPTH = 6
SIM_TIME_LIMIT_S = 0.1
# Advantage in hundredths of a pawn from which an unfinished game is awarded as a win.
ADJUDICATE_CP = 300
# How many best moves are evaluated: the participant chooses only among them, so in a position with a single move
# the number of bad options is limited.
SIM_CANDIDATES = 8
# "Temperature" of move choice by rating, cp: a move with loss T is chosen e times less often than the best, beyond that
# the weight falls steeper (power LOSS_POWER) - a piece blunder is rare even for a weak one. Measurement of 17.11 (16 games
# per pair, a game ~ 1 s): a 200-point difference - 69-78 % of points to the stronger (by Elo 76 %), 400 - 94-97 % (91 %),
# 800 - 100 % (99 %).
SIM_TEMPERATURE: tuple[tuple[int, float], ...] = ((800, 260.0), (1200, 170.0), (1600, 110.0), (2000, 65.0),
                                                  (2400, 32.0), (2800, 12.0))
# Power in the move weight formula: above 1 - a small loss is barely penalised, a large one sharply.
LOSS_POWER = 1.5


def temperature_cp(rating: int) -> float:
    """Move choice temperature for a rating: linear between the SIM_TEMPERATURE anchor points."""
    points = SIM_TEMPERATURE
    if rating <= points[0][0]:
        return points[0][1]
    for (lo_elo, lo_t), (hi_elo, hi_t) in zip(points, points[1:], strict=False):
        if rating <= hi_elo:
            return lo_t + (hi_t - lo_t) * (rating - lo_elo) / (hi_elo - lo_elo)
    return points[-1][1]


def move_weights(
        scores: dict[chess.Move, float], style: dict[chess.Move, float], temperature: float,
) -> dict[chess.Move, float]:
    """
    Move weights: exp(-(loss / T)^LOSS_POWER), loss is the evaluation's lag behind the best move. Style shifts the loss
    by no more than half the temperature: character is visible, but a bad move does not become a good one.
    """
    best = max(scores.values())
    weights = {}
    for move, cp in scores.items():
        bonus = max(-temperature / 2, min(temperature / 2, style.get(move, 0.0)))
        loss = max(0.0, best - cp - bonus)
        weights[move] = math.exp(-((loss / temperature) ** LOSS_POWER))
    return weights


class SimulatedPlayer:
    """A participant of a bot game: moves from its opening book, then by the simulation's strength model (see the module)."""

    def __init__(self, bot: HistoricalBot, rating: int, rng: random.Random | None = None):
        """rating sets the move choice temperature; rng is replaced in tests for reproducibility."""
        self.bot = bot
        self.rating = rating
        self.temperature = temperature_cp(rating)
        self.rng = rng or random.Random()

    def choose_move(self, fen: str) -> dict:
        """
        A simulation participant's move: from the opening book, otherwise random among the best moves with a weight that
        falls with the loss in evaluation (the lower the rating, the weaker it falls) and grows with the style bonus.
        """
        board = chess.Board(fen)
        book = self.bot._book_move(board)
        if book is not None:
            return {"uci": book[0].uci(), "source": "opening_book"}
        engine_path = self.bot._get_active_engine_path() if self.bot.stockfish_path is not None else None
        scores = analyse_with_stockfish(
            board=board, engine_path=engine_path, depth=self.bot.search_depth, time_limit=self.bot.time_limit,
            multipv=SIM_CANDIDATES,
        ) or fallback_scores(board)
        style = {move: self.bot.evaluate_style_bonus(board, move)[0] for move in scores}
        weights = move_weights(scores, style, self.temperature)
        moves = list(weights)
        move = self.rng.choices(moves, weights=[weights[m] for m in moves], k=1)[0]
        return {"uci": move.uci(), "source": "simulation"}


def simulation_rating(player: TournamentPlayer, historic: bool = False) -> int:
    """
    A participant's strength in bot games. Usually the strength at the start of the tournament (for a bot - measured by
    calibration: that is also what it is in a game with the player). In a "Time Machine" tournament (historic) a historical
    bot gets its stated strength: it reflects the master's place in history, while the measured one is sometimes noticeably
    lower (Chigorin - 1833 against a stated 2150), and the Hastings runner-up would take last place. The player's rating is
    still computed from the measured strength.
    """
    from src.api.bots import BOT_METADATA

    if historic and player.kind == "bot" and player.bot_key in BOT_METADATA:
        return int(str(BOT_METADATA[player.bot_key]["rating"]))
    return player.rating


def player_for(player: TournamentPlayer, historic: bool = False) -> SimulatedPlayer:
    """A simulation participant: their bot (book, style) and strength (simulation_rating)."""
    return SimulatedPlayer(bot_for(player), simulation_rating(player, historic))


def bot_for(player: TournamentPlayer) -> HistoricalBot:
    """A participant's bot with search depth and time lowered for the simulation."""
    from src.services.bots import BOT_INSTANCES
    from src.services.bots.archetypes import ARCHETYPES_BY_KEY
    from src.services.bots.personality import BotPersonalityConfig, PersonalityBot

    bot: HistoricalBot
    if player.kind == "bot" and player.bot_key in BOT_INSTANCES:
        bot = type(BOT_INSTANCES[player.bot_key])()
    elif player.kind == "archetype" and player.bot_key in ARCHETYPES_BY_KEY:
        bot = PersonalityBot(selfplay.tuned_config(ARCHETYPES_BY_KEY[player.bot_key]))
    elif player.kind == "personality" and player.config_json:
        bot = PersonalityBot(BotPersonalityConfig.model_validate_json(player.config_json))
    else:
        raise ValueError(f"seat {player.seat} is not a bot ({player.kind})")
    bot.search_depth = min(bot.search_depth, SIM_MAX_DEPTH)
    bot.time_limit = min(bot.time_limit, SIM_TIME_LIMIT_S)
    return bot


def adjudicate(board: chess.Board) -> str:
    """Result of an unfinished game: an advantage above ADJUDICATE_CP by the engine (or static) evaluation - a win."""
    scores = analyse_with_stockfish(
        board=board, engine_path=resolve_stockfish_path(), depth=12,
        time_limit=0.2, multipv=1,
    )
    if scores:
        cp = max(scores.values())
        white_cp = cp if board.turn == chess.WHITE else -cp
    else:
        white_cp = static_board_eval_cp(board, chess.WHITE)
    if white_cp > ADJUDICATE_CP:
        return "1-0"
    if white_cp < -ADJUDICATE_CP:
        return "0-1"
    return "1/2-1/2"


def play_game(
        white: HistoricalBot | SimulatedPlayer, black: HistoricalBot | SimulatedPlayer,
        max_plies: int = SIM_MAX_PLIES, judge: Callable[[chess.Board], str] = adjudicate,
) -> tuple[list[str], str, str]:
    """
    Bot against bot game: (uci moves, result, termination reason). A game unfinished by max_plies is decided by
    judge, the reason is then "adjudication".
    """
    board = chess.Board()
    moves: list[str] = []
    while not board.is_game_over(claim_draw=True) and board.ply() < max_plies:
        bot = white if board.turn == chess.WHITE else black
        uci = bot.choose_move(board.fen())["uci"]
        board.push_uci(uci)
        moves.append(uci)
    if board.is_game_over(claim_draw=True):
        outcome = board.outcome(claim_draw=True)
        termination = outcome.termination.name.lower() if outcome else "normal"
        return moves, board.result(claim_draw=True), termination
    return moves, judge(board), "adjudication"


async def claim(db: AsyncSession, game_id: int) -> bool:
    """Takes a tournament game for simulation; False - another worker is already computing it or it has been played."""
    now = datetime.now(UTC)
    result = await db.execute(
        update(TournamentGame)
        .where(
            TournamentGame.id == game_id,
            TournamentGame.result.is_(None),
            or_(TournamentGame.started_at.is_(None), TournamentGame.started_at < now - tournaments.CLAIM_TIMEOUT),
        )
        .values(started_at=now)
    )
    await db.commit()
    return bool(getattr(result, "rowcount", 0))


def _pgn_name(player: TournamentPlayer) -> str:
    """Participant name for the PGN: a historical bot, an archetype or a personality; without a name - a neutral entry."""
    from src.api.bots import BOT_METADATA
    from src.services.bots.archetypes import ARCHETYPES_BY_KEY

    if player.kind == "bot" and player.bot_key in BOT_METADATA:
        return str(BOT_METADATA[player.bot_key]["pgn_name"])
    if player.kind == "archetype" and player.bot_key in ARCHETYPES_BY_KEY:
        return ARCHETYPES_BY_KEY[player.bot_key].pgn_name
    return player.personality_name or "Workshop opponent"


async def save_and_record(
        db: AsyncSession, tournament: Tournament, tgame: TournamentGame, moves: list[str], result: str,
        termination: str,
) -> list[int]:
    """
    Saves the game (PGN, the is_simulation mark), writes the result into the tournament and advances it. Returns the ids of
    games that should be queued (tournaments.mark_for_queue).
    """
    from src.api.bots import CUSTOM_BOT_ID, _build_pgn_string, _get_or_create_bot_user
    from src.services.openings import eco_code

    seats = {p.seat: p for p in await tournaments.players_of(db, tournament.id)}
    white, black = seats[tgame.white_seat], seats[tgame.black_seat]

    async def user_id(player: TournamentPlayer) -> int:
        bot_id = player.bot_key if player.kind == "bot" and player.bot_key else CUSTOM_BOT_ID
        return (await _get_or_create_bot_user(db, bot_id)).id

    pgn_text, final_fen = _build_pgn_string(
        moves_uci=moves, white_name=_pgn_name(white), white_elo=white.rating,
        black_name=_pgn_name(black), black_elo=black.rating, result=result,
    )
    now = datetime.now(UTC)
    game = Game(
        white_player_id=await user_id(white), black_player_id=await user_id(black), pgn=pgn_text, board_fen=final_fen,
        result=result, termination=termination, is_rated=False, base_time_ms=tgame.base_time_ms,
        increment_ms=tgame.increment_ms, status=GameStatus.COMPLETED, finished_at=now,
        pgn_date=now.strftime("%Y.%m.%d"), site="Regence Tournament", eco=eco_code(moves), is_simulation=True,
    )
    db.add(game)
    await db.flush()
    await tournaments.record_result(db, tournament, tgame, result, game.id)
    await db.refresh(tournament)
    return await tournaments.mark_for_queue(db, tournament)


async def simulate(db: AsyncSession, tournament_game_id: int, play: Callable = play_game) -> list[int]:
    """
    Plays a tournament game between bots and records it. Returns the ids of the next games for simulation
    (empty if the game was already taken by another worker or the tournament is closed).
    """
    if not await claim(db, tournament_game_id):
        return []
    tgame = await db.get(TournamentGame, tournament_game_id)
    tournament = await db.get(Tournament, tgame.tournament_id) if tgame else None
    if tgame is None or tournament is None or tournament.status != "active":
        return []
    seats = {p.seat: p for p in await tournaments.players_of(db, tournament.id)}
    historic = tournament.event_key is not None
    white_seat, black_seat = seats[tgame.white_seat], seats[tgame.black_seat]
    await selfplay.refresh(db)
    for seat in (white_seat, black_seat):
        if _historical_bot_key(seat):
            await bot_memory.refresh(db, seat.bot_key or "")
    # A game is processor work: in a separate thread, so as not to hold the event loop.
    with engine_work("simulation"):
        moves, result, termination = await asyncio.to_thread(
            play, player_for(white_seat, historic), player_for(black_seat, historic),
        )
    logger.info("Tournament %s game %s: %s in %d plies", tournament.id, tgame.id, result, len(moves))
    following = await save_and_record(db, tournament, tgame, moves, result, termination)
    await _remember_openings(db, white_seat, black_seat, moves, result)
    return following


def _historical_bot_key(player: TournamentPlayer) -> str | None:
    """Key of the participant's historical bot (it has a book and an opening memory); None for the others."""
    from src.services.bots import BOT_INSTANCES

    return player.bot_key if player.kind == "bot" and player.bot_key in BOT_INSTANCES else None


async def _remember_openings(db: AsyncSession, white: TournamentPlayer, black: TournamentPlayer, moves: list[str],
                             result: str) -> None:
    """Bot tournament experience (task 32.1): the result goes to the historical bots' opening moves; no effect on rating."""
    from src.services.bots import BOT_INSTANCES

    for player, color in ((white, chess.WHITE), (black, chess.BLACK)):
        key = _historical_bot_key(player)
        if key is None:
            continue
        try:
            await bot_memory.record_book(db, key, BOT_INSTANCES[key].opening_book, moves, color, result)
        except Exception as exc:  # the game is already recorded in the tournament - the experience is not critical
            await db.rollback()
            logger.warning("Bot memory update failed for %s: %s", key, exc)
