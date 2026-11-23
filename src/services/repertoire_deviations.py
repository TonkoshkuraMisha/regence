"""
Deviations from the repertoire in a played game (task 20.3). The game is walked by positions (not by moves), so
transpositions are recognised. For each repertoire of its own colour - the first place where the game left the tree:

* `you_left` - the player played not their own move (the repertoire has another one here);
* `opponent_new` - the opponent played a move that is not in the repertoire ("add a reply?");
* `end` - the game reached the end of the prepared line;
* `followed` - the whole game followed the repertoire.

Stores nothing: the repertoire tree is built by src/services/repertoire.build_tree from repertoire_moves, the game's moves
are the main line of the PGN of the finished game (game_moves). The check of all the player's repertoires is done by
for_game; it is served by the route GET /repertoires/game/{id}/deviations (src/api/repertoire.py) and the post-game cards
(src/services/coach_cards.py).
"""

import io
from dataclasses import dataclass

import chess
import chess.pgn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.game import Game
from src.models.repertoire import Repertoire
from src.services import repertoire as service


@dataclass(frozen=True)
class Deviation:
    """The place where the game diverged from the repertoire (or the result "followed in full")."""

    kind: str
    ply: int  # game ply (from 1) at which the tree was left; for followed - the game length
    played: str | None  # SAN
    played_uci: str | None
    expected: list[str]  # repertoire moves from this position (SAN); empty for end and followed
    line: list[str]  # moves up to the deviation position
    position: str  # key of the deviation position (EPD, repertoire.position_key)


def find(repertoire: Repertoire, edges: list[service.Edge], moves: list[chess.Move]) -> Deviation | None:
    """
    The first divergence of the game from the repertoire. None - there is nothing to compare with: the game has no moves or
    the repertoire has no moves from the starting position. If, however, the game's first move did not match the
    repertoire, this is a deviation on the first ply (you_left or opponent_new), not None.
    """
    by_position: dict[str, list[service.Edge]] = {}
    for edge in edges:
        by_position.setdefault(edge.position, []).append(edge)
    side = chess.WHITE if repertoire.color == "white" else chess.BLACK
    board = chess.Board()
    for index, move in enumerate(moves):
        key = service.position_key(board)
        options = by_position.get(key, [])
        line = [m.uci() for m in moves[:index]]
        if not options:
            return Deviation("end", index + 1, None, None, [], line, key) if index else None
        if move.uci() not in {e.uci for e in options}:
            kind = "you_left" if board.turn == side else "opponent_new"
            return Deviation(kind, index + 1, board.san(move), move.uci(), [e.san for e in options], line, key)
        board.push(move)
    return Deviation("followed", len(moves), None, None, [], [m.uci() for m in moves],
                     service.position_key(board)) \
        if moves else None


def game_moves(pgn: str | None) -> list[chess.Move]:
    """Main line of a game from the starting position; games with a special setup are not compared (an empty list)."""
    parsed = chess.pgn.read_game(io.StringIO(pgn or ""))
    if parsed is None or parsed.board().fen() != chess.STARTING_FEN:
        return []
    return list(parsed.mainline_moves())


async def for_game(db: AsyncSession, game: Game, user_id: int) -> dict:
    """
    Where the game left each repertoire of the player's colour: {color, results}. results - one per repertoire
    (repertoire_id, name, starter, kind, ply, played, played_uci, expected, line, position), the latest
    deviations first. The check "own finished game" is done by the caller.
    """
    color = "white" if game.white_player_id == user_id else "black"
    moves = game_moves(game.pgn)
    repertoires = (await db.execute(
        select(Repertoire).where(Repertoire.user_id == user_id, Repertoire.color == color).order_by(Repertoire.id)
    )).scalars().all()
    results: list[dict] = []
    for repertoire in repertoires:
        edges = service.build_tree(repertoire.color, await service.load_moves(db, repertoire.id))
        found = find(repertoire, edges, moves)
        if found is None:
            continue
        results.append({"repertoire_id": repertoire.id, "name": repertoire.name, "starter": repertoire.starter,
                        "kind": found.kind, "ply": found.ply, "played": found.played, "played_uci": found.played_uci,
                        "expected": found.expected, "line": found.line, "position": found.position})
    results.sort(key=lambda r: -int(r["ply"]))
    return {"color": color, "results": results}
