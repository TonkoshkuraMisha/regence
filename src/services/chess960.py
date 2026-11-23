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
from dataclasses import dataclass

import chess
import chess.engine

from src.core.errors import DomainValueError
from src.services.bots.base import resolve_stockfish_path
from src.services.engine_pool import EngineUnavailableError, get_engine_pool

# Number of the ordinary starting setup in Fischer chess numbering (0-959).
STANDARD_POSITION = 518
# How many half-moves the server replays; moves beyond this number are dropped (protection against an overly long request).
MAX_PLIES = 600
# Bot levels: Stockfish strength limit (UCI_Elo not below 1320) and time per move in seconds. An unknown level
# plays as the second.
LEVELS: dict[int, tuple[int, float]] = {1: (1320, 0.05), 2: (1600, 0.1), 3: (1900, 0.15), 4: (2200, 0.25),
                                        5: (2600, 0.4)}


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
