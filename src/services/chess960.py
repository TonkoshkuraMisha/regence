"""
Fischer chess (task 21.3): a random setup out of 960, a game against a bot. The rules (including castling by
the 960 rules) are `python-chess` in chess960 mode, the bot is Stockfish with `UCI_Chess960` (python-chess enables the option
itself
from the board flag) and a strength limit via the engine pool (rule 3). The client sends the setup number and the moves from
the start of the game: the server replays them, so it also sees position repetitions. No rating and the game is not stored.

Castling in moves is "the king takes its own rook" (960-mode UCI, e.g. e1h1), which specifies it unambiguously for any
setup.
"""

import random
from dataclasses import dataclass, field

import chess
import chess.engine

from src.core.errors import DomainValueError
from src.services.bots.base import resolve_stockfish_path
from src.services.engine_pool import EngineUnavailableError, get_engine_pool
from src.services.game_engine import CHESS960_VARIANT, is_chess960_fen, read_pgn_game

# Number of the ordinary starting setup in Fischer chess numbering (0-959).
STANDARD_POSITION = 518
# How many half-moves the server replays; moves beyond this number are dropped (protection against an overly long request).
MAX_PLIES = 600
# Bot levels: Stockfish strength limit (UCI_Elo not below 1320) and time per move in seconds. An unknown level
# plays as the second.
LEVELS: dict[int, tuple[int, float]] = {1: (1320, 0.05), 2: (1600, 0.1), 3: (1900, 0.15), 4: (2200, 0.25),
                                        5: (2600, 0.4)}


# Analysis of a finished game: at most this many positions are evaluated, each for this many seconds at full strength;
# a mate is mapped to this centipawn magnitude so that the curve stays plottable.
MAX_ANALYSIS_POSITIONS = 161
ANALYSIS_SECONDS = 0.05
MATE_SCORE_CP = 10000


@dataclass
class Game:
    """A replayed game: the setup number, the board after all moves and these moves in SAN notation."""
    number: int
    board: chess.Board
    sans: list[str]


def start_board(number: int) -> chess.Board:
    """The starting board of setup number (0-959) in chess960 mode; another number — chess960_bad_position."""
    if not 0 <= number <= 959:
        raise DomainValueError("chess960_bad_position")
    return chess.Board.from_chess960_pos(number)


def random_number(rng: random.Random | None = None) -> int:
    return (rng or random.Random()).randrange(960)


def replay(number: int, moves: list[str]) -> Game:
    """
    A game from setup number by UCI moves; an illegal move — an error with this move, a move after the end of the game —
    mini_game_over. The first MAX_PLIES moves are taken.
    """
    board = start_board(number)
    sans: list[str] = []
    for uci in moves[:MAX_PLIES]:
        sans.append(push(board, uci))
    return Game(number, board, sans)


def push(board: chess.Board, uci: str) -> str:
    """
    Applies the player's move (960-mode UCI notation) and returns its SAN. An illegal move or an already finished game —
    a refusal.
    """
    if outcome(board)[0] is not None:
        raise DomainValueError("mini_game_over")
    try:
        move = board.parse_uci(uci)
    except ValueError:
        raise DomainValueError("illegal_move", move=uci[:10]) from None
    san = board.san(move)
    board.push(move)
    return san


def outcome(board: chess.Board) -> tuple[str | None, str | None]:
    """
    Result and reason: mate, stalemate, insufficient material; threefold repetition and 50 moves — when they have already
    happened
    (claim_draw in python-chess would count a draw a move earlier: "the next move can repeat"). Returns
    (result "1-0" | "0-1" | "1/2-1/2", reason) or (None, None) while the game is in progress.
    """
    result = board.outcome()
    if result is not None:
        return result.result(), result.termination.name.lower()
    if board.is_repetition(3):
        return "1/2-1/2", "threefold_repetition"
    if board.is_fifty_moves():
        return "1/2-1/2", "fifty_moves"
    return None, None


def bot_move(board: chess.Board, level: int) -> chess.Move:
    """
    The bot's move in a Fischer game: Stockfish from the pool with a strength and time limit by level (LEVELS). No engine or it
    returned no legal move — EngineUnavailableError; the pool is busy — EngineBusyError (the route responds with a refusal).
    """
    elo, seconds = LEVELS.get(level, LEVELS[2])
    path = resolve_stockfish_path()
    if path is None:
        raise EngineUnavailableError("Stockfish path is not configured")
    with get_engine_pool(path).acquire({"UCI_LimitStrength": True, "UCI_Elo": elo}) as engine:
        played = engine.play(board, chess.engine.Limit(time=seconds))
    if played.move is None or played.move not in board.legal_moves:
        raise EngineUnavailableError("engine returned no legal move")
    return played.move


@dataclass
class Record:
    """A finished Fischer game for replay: the start (Shredder) FEN, the moves (UCI and SAN) and the FEN after every ply."""
    start_fen: str
    moves: list[str] = field(default_factory=list)
    sans: list[str] = field(default_factory=list)
    fens: list[str] = field(default_factory=list)
    result: str | None = None

    def view(self, game_id: int) -> dict:
        """The record for the client's 960 viewer (site archive and imported games), under the given game id."""
        return {"game_id": game_id, "start_fen": self.start_fen, "fens": self.fens, "moves": self.moves,
                "sans": self.sans, "result": self.result}


def archive_record(pgn: str) -> Record:
    """
    Replays a stored game record (games.pgn, task 21.3 archive). A game that is not Fischer chess (no `Variant "Chess960"`
    header and a start FEN without Shredder castling letters) or an unreadable record is `not_chess960_game`. `fens[0]` is the
    start position, `fens[i]` the position after ply i, so the client can step through the game without any chess rules.
    """
    game = read_pgn_game(pgn)
    start = game.headers.get("FEN") if game is not None else None
    if game is None or game.errors or not start or not (
            game.headers.get("Variant") == CHESS960_VARIANT or is_chess960_fen(start)):
        raise DomainValueError("not_chess960_game")
    board = game.board()
    record = Record(start_fen=board.fen(shredder=True), fens=[board.fen(shredder=True)], result=game.headers.get("Result"))
    for move in game.mainline_moves():
        record.sans.append(board.san(move))
        record.moves.append(move.uci())
        board.push(move)
        record.fens.append(board.fen(shredder=True))
    return record


def evaluate_positions(fens: list[str]) -> list[int]:
    """
    Stockfish evaluation (centipawns from White's point of view, a mate is +-MATE_SCORE_CP) of each position of a game, for the
    archive analysis curve. Full strength, ANALYSIS_SECONDS per position, at most MAX_ANALYSIS_POSITIONS positions; the
    engine is used through the pool (rule 3). No engine - EngineUnavailableError, a busy pool - EngineBusyError.
    """
    path = resolve_stockfish_path()
    if path is None:
        raise EngineUnavailableError("Stockfish path is not configured")
    scores: list[int] = []
    with get_engine_pool(path).acquire({}) as engine:
        for fen in fens[:MAX_ANALYSIS_POSITIONS]:
            board = chess.Board(fen, chess960=True)
            if board.is_game_over():
                outcome_result = board.outcome()
                winner = outcome_result.winner if outcome_result else None
                scores.append(0 if winner is None else (MATE_SCORE_CP if winner else -MATE_SCORE_CP))
                continue
            info = engine.analyse(board, chess.engine.Limit(time=ANALYSIS_SECONDS))
            scores.append(info["score"].white().score(mate_score=MATE_SCORE_CP))
    return scores
