"""
Opening repertoire (task 20.1): lines from the explorer, from PGN and from one's own games are put together into a graph of
positions (src/models/repertoire.py). The client receives edges with SAN and the position key after the move and walks the
tree without computing keys itself; it sends new moves as a UCI line from the starting position.

Data: repertoires (name, colour, owner) and repertoire_moves - the graph edges: a position (EPD), a move from it and a
comment. A position is stored once, however it is reached, so transpositions merge. The repetition cards
(repertoire_cards) are managed by src/services/repertoire_drill.py. The module's functions do not commit - the route
(src/api/repertoire.py) does.
"""

import io
from collections import deque
from dataclasses import dataclass

import chess
import chess.pgn
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DomainValueError
from src.models.repertoire import Repertoire, RepertoireMove
from src.services.repertoire_starters import Starter

MAX_REPERTOIRES = 20  # repertoires per player (checked by the creation route)
MAX_MOVES = 2000  # moves (edges) in one repertoire
MAX_LINE_PLIES = 40  # line depth in plies: a longer line is silently truncated
MAX_PGN_CHARS = 100_000  # limit on the PGN text size on import
MAX_PGN_GAMES = 50  # no more than this many games are read from the PGN text, the rest are not considered
MAX_COMMENT = 300  # length of a move comment (checked by the request schema)
ROOT = chess.Board().epd()  # key of the starting position - the root of the tree


def position_key(board: chess.Board) -> str:
    """Position key in the graph - EPD: placement, side to move, castling, en passant (without move counters)."""
    return board.epd()


@dataclass(frozen=True)
class Edge:
    """
    A tree edge for the client: a position, a move from it (UCI and SAN), the position after the move, a comment and whose
    move it is (mine - a move of the side the repertoire is built for).
    """

    position: str
    uci: str
    san: str
    child: str
    comment: str
    mine: bool


def parse_line(moves_uci: list[str]) -> list[tuple[str, str]]:
    """
    UCI line from the starting position -> (position, move) pairs; an illegal move is an error carrying that move. The first
    MAX_LINE_PLIES plies are taken into account.
    """
    board = chess.Board()
    pairs = []
    for uci in moves_uci[:MAX_LINE_PLIES]:
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            raise DomainValueError("illegal_move", move=uci[:10]) from None
        if move not in board.legal_moves:
            raise DomainValueError("illegal_move", move=uci)
        pairs.append((position_key(board), move.uci()))
        board.push(move)
    return pairs


def san_line_to_uci(line: str) -> list[str]:
    """A line in SAN separated by spaces (no move numbers) -> UCI moves. For our own data (ready sets): no checks."""
    board = chess.Board()
    moves = []
    for san in line.split():
        move = board.parse_san(san)
        moves.append(move.uci())
        board.push(move)
    return moves


def starter_lines(starter: Starter) -> list[list[str]]:
    """Lines of a ready-made repertoire (src/services/repertoire_starters.py) in UCI - for ``add_lines``."""
    return [san_line_to_uci(line) for line in starter.lines]


def pgn_lines(text: str) -> list[list[str]]:
    """
    All lines (main and variations) of all games of the PGN text; games not from the starting position and games with parse
    errors are skipped. No more than MAX_PGN_GAMES games are read, each line up to MAX_LINE_PLIES plies.
    Too long a text or no lines at all - refusal repertoire_bad_pgn. PGN comments are not carried over.
    """
    if len(text) > MAX_PGN_CHARS:
        raise DomainValueError("repertoire_bad_pgn")
    handle = io.StringIO(text)
    lines: list[list[str]] = []
    for _ in range(MAX_PGN_GAMES):
        game = chess.pgn.read_game(handle)
        if game is None:
            break
        if game.errors or game.board().epd() != ROOT:
            continue
        stack: list[tuple[chess.pgn.GameNode, list[str]]] = [(game, [])]
        while stack:
            node, path = stack.pop()
            if not node.variations or len(path) >= MAX_LINE_PLIES:
                if path:
                    lines.append(path)
                continue
            for child in node.variations:
                stack.append((child, [*path, child.move.uci()]))
    if not lines:
        raise DomainValueError("repertoire_bad_pgn")
    return lines


def build_tree(color: str, rows: list[RepertoireMove]) -> list[Edge]:
    """
    Edges reachable from the starting position, in breadth-first order (short lines first). Moves from one
    position go in the order of addition (by id). A position reached by different move orders is expanded
    once. Rows unreachable from the root and illegal moves do not enter the result.
    """
    by_position: dict[str, list[RepertoireMove]] = {}
    for row in sorted(rows, key=lambda r: r.id):
        by_position.setdefault(row.position, []).append(row)
    side = chess.WHITE if color == "white" else chess.BLACK
    edges: list[Edge] = []
    seen = {ROOT}
    queue = deque([chess.Board()])
    while queue:
        board = queue.popleft()
        key = position_key(board)
        for row in by_position.get(key, []):
            move = chess.Move.from_uci(row.move_uci)
            if move not in board.legal_moves:
                continue
            san = board.san(move)
            child = board.copy(stack=False)
            child.push(move)
            child_key = position_key(child)
            edges.append(Edge(key, row.move_uci, san, child_key, row.comment, board.turn == side))
            if child_key not in seen:
                seen.add(child_key)
                queue.append(child)
    return edges


async def load_moves(db: AsyncSession, repertoire_id: int) -> list[RepertoireMove]:
    return list((await db.execute(
        select(RepertoireMove).where(RepertoireMove.repertoire_id == repertoire_id)
    )).scalars().all())


async def count_moves(db: AsyncSession, repertoire_id: int) -> int:
    return await db.scalar(
        select(func.count()).select_from(RepertoireMove).where(RepertoireMove.repertoire_id == repertoire_id)
    ) or 0


async def add_lines(db: AsyncSession, repertoire: Repertoire, lines: list[list[str]]) -> int:
    """Adds the moves of lines that are not there yet; beyond MAX_MOVES - an error, nothing is added."""
    existing = {(row.position, row.move_uci) for row in await load_moves(db, repertoire.id)}
    new: dict[tuple[str, str], None] = {}
    for line in lines:
        for pair in parse_line(line):
            if pair not in existing:
                new[pair] = None
    if len(existing) + len(new) > MAX_MOVES:
        raise DomainValueError("repertoire_too_large", limit=MAX_MOVES)
    db.add_all(RepertoireMove(repertoire_id=repertoire.id, position=position, move_uci=uci)
               for position, uci in new)
    return len(new)


async def remove_move(db: AsyncSession, repertoire: Repertoire, position: str, uci: str) -> int:
    """Removes a move and all that became unreachable from the starting position after it; returns the number removed."""
    rows = await load_moves(db, repertoire.id)
    target = next((row for row in rows if row.position == position and row.move_uci == uci), None)
    if target is None:
        raise DomainValueError("repertoire_move_not_found")
    rest = [row for row in rows if row is not target]
    reachable = {(edge.position, edge.uci) for edge in build_tree(repertoire.color, rest)}
    doomed = [target.id, *(row.id for row in rest if (row.position, row.move_uci) not in reachable)]
    await db.execute(delete(RepertoireMove).where(RepertoireMove.id.in_(doomed)))
    return len(doomed)
