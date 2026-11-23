"""
"Miniatures" (task 27.9): short library games that ended in mate on the board. The exercise is the position before
the last move: find the mate (any mating move is accepted). No engine is needed: python-chess verifies the mate.

Data: the library_games table. Selection is done by the route GET /library/miniatures (src/api/library.py): public games
from the ordinary starting position, with the mate_finish flag and no longer than MAX_PLIES plies, in random order; this
module re-checks each one by its moves and builds the task. The answer (the game's move) goes to the client - the exercise
has no rating, verification is on the client.
"""

import random
from dataclasses import dataclass

import chess

MAX_PLIES = 50  # up to 25 moves


@dataclass(frozen=True)
class Miniature:
    game_id: int
    fen: str
    moves: list[str]  # moves of the game up to the task position
    answer: str  # the game's move (UCI)


def miniature(game_id: int, moves_text: str) -> Miniature | None:
    """
    A game is a miniature if the last move gave mate. moves_text is the game's moves in UCI separated by spaces
    (library_games.moves). None - the game is longer than MAX_PLIES, shorter than two plies, has an unreadable or
    illegal move, or has no mate at the end.
    """
    moves = moves_text.split()
    if not 2 <= len(moves) <= MAX_PLIES:
        return None
    board = chess.Board()
    try:
        for uci in moves[:-1]:
            board.push(chess.Move.from_uci(uci))
        last = chess.Move.from_uci(moves[-1])
    except (ValueError, AssertionError):
        return None
    if last not in board.legal_moves:
        return None
    fen = board.fen()
    board.push(last)
    if not board.is_checkmate():
        return None
    return Miniature(game_id, fen, moves[:-1], moves[-1])


def pick(rows: list[tuple[int, str]], count: int, rng: random.Random) -> list[Miniature]:
    """At most count miniatures from rows (game id, moves) in random order; an rng with a seed makes the set reproducible."""
    found = [m for m in (miniature(game_id, moves) for game_id, moves in rows) if m is not None]
    rng.shuffle(found)
    return found[:count]
