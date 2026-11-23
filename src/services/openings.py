# --- FILE: src/services/openings.py ---
"""
Opening detection (task 16.1): one table instead of two copies of hard-coded prefixes (game_state.py, api/bots.py).
Data - src/services/data/openings.tsv (built by scripts/build_openings.py from the open lichess set, CC0).

The opening is determined by position: we walk the game's moves and remember the last position that is in the table - this way
transpositions are recognised too. The names are English proper nouns from the set (like player names), not translated.

The table (3865 rows as of 17.11.2026; columns eco, name, epd, uci) is read from disk once per process and stays in
memory. A position is compared by EPD: piece placement, side to move, castling rights and the en passant square.
"""

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import chess

DATA = Path(__file__).resolve().parent / "data" / "openings.tsv"
# How many plies of a game are scanned: there is no table deeper (the longest set entry is 36 plies).
MAX_PLIES = 40
UNKNOWN_ECO = "A00"  # ECO code when no position of the game is found in the table ("irregular openings")


@dataclass(frozen=True)
class Opening:
    """Opening: the ECO code and the English name from the table."""

    eco: str
    name: str


@dataclass(frozen=True)
class OpeningLine:
    """A table record with moves - for the favourite openings of the workshop opponents (task 21.2)."""

    eco: str
    name: str
    epd: str
    moves: tuple[str, ...]


@lru_cache(maxsize=1)
def lines() -> dict[str, OpeningLine]:
    """The whole table with moves, keyed by the position (EPD) at the end of the line. Read once and shared: do not modify."""
    with DATA.open(encoding="utf-8") as handle:
        return {row["epd"]: OpeningLine(row["eco"], row["name"], row["epd"], tuple(row["uci"].split()))
                for row in csv.DictReader(handle, delimiter="\t")}


def search(query: str, limit: int = 20) -> list[OpeningLine]:
    """Openings by part of the name or by ECO code: first names starting with the query, within them - short lines."""
    text = query.strip().lower()
    if not text:
        return []
    found = [line for line in lines().values()
             if text in line.name.lower() or line.eco.lower().startswith(text)]
    return sorted(found, key=lambda line: (not line.name.lower().startswith(text), len(line.moves), line.eco,
                                           line.name))[:limit]


@lru_cache(maxsize=1)
def _table() -> dict[str, Opening]:
    """Position (EPD) -> opening: the same table without moves, for determining a game's opening."""
    with DATA.open(encoding="utf-8") as handle:
        return {row["epd"]: Opening(row["eco"], row["name"]) for row in csv.DictReader(handle, delimiter="\t")}


def classify_board_line(board: chess.Board, moves: list[chess.Move]) -> Opening | None:
    """
    Opening by moves from the start position board (usually the initial one): the last position of the line found in the table.
    No more than MAX_PLIES plies are scanned; at the first illegal move scanning stops. The passed
    board is not modified. None - no position from the table was met.
    """
    table = _table()
    found = table.get(board.epd())
    board = board.copy(stack=False)
    for move in moves[:MAX_PLIES]:
        if move not in board.legal_moves:
            break
        board.push(move)
        found = table.get(board.epd(), found)
    return found


def classify(moves_uci: list[str]) -> Opening | None:
    """Opening of a game from the initial position by UCI moves; None - there were no moves from the table."""
    moves = []
    for uci in moves_uci[:MAX_PLIES]:
        try:
            moves.append(chess.Move.from_uci(uci))
        except ValueError:
            break
    return classify_board_line(chess.Board(), moves)


def eco_code(moves_uci: list[str]) -> str:
    """
    ECO code for the PGN header and the games.eco column; an unknown opening is A00. Called by the finishing of a game between
    humans (game_state.py), saving a game with a bot (api/bots.py) and the tournament simulation (tournament_simulation.py).
    """
    opening = classify(moves_uci)
    return opening.eco if opening else UNKNOWN_ECO
