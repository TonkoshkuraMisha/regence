# --- FILE: src/services/collections.py ---
"""
"Fun collections" of the archive (task 16.3). Metrics are computed for each game (game_metrics), and places in the
collections from them (rank_collections). The collections:

* shortest — the shortest games that ended in mate (no-shows and instant resignations are not "short games");
* checks — the most checks;
* capture_streak — the longest streak of consecutive captures;
* peaceful — the most peaceful: the fewest captures, on a tie — the longer game (without captures — first);
* promotions — the most promotions;
* pawn_wars — the most passed pawns on the board at once;
* stalemates — "triumphant draws": the game ended in stalemate (the longest first).

The module only computes. The collections table (collection_entries) is filled by scripts/build_collections.py from the PGN of
the archive
games, and it is served by the "Browse" section (src/api/watch.py).
"""

import io
import zlib
from dataclasses import dataclass

import chess
import chess.pgn

# Collection codes (the client takes names from the catalogs by them) and the number of games in each.
COLLECTIONS = ("shortest", "checks", "capture_streak", "peaceful", "promotions", "pawn_wars", "stalemates")
PER_COLLECTION = 10
MIN_PEACEFUL_PLIES = 40   # a short game without captures is not "peaceful" but just short (40 half-moves — 20 moves)


@dataclass(frozen=True)
class Metrics:
    """
    Metrics of one game for the collections: length, checks, captures and their longest streak, promotions, passed pawns,
    mate or stalemate.
    """
    plies: int
    decisive: bool
    checks: int
    captures: int
    capture_streak: int
    promotions: int
    passed_pawns: int
    stalemate: bool
    checkmate: bool
    # Move signature: the archive has duplicates of one game — in a collection each game appears once.
    signature: int


def passed_pawns(board: chess.Board) -> int:
    """Number of passed pawns of both sides: ahead on its own and adjacent files there are no opponent pawns."""
    total = 0
    for color in (chess.WHITE, chess.BLACK):
        enemy = board.pieces(chess.PAWN, not color)
        for square in board.pieces(chess.PAWN, color):
            file, rank = chess.square_file(square), chess.square_rank(square)
            ahead = range(rank + 1, 8) if color == chess.WHITE else range(rank - 1, -1, -1)
            blocked = any(
                chess.square(f, r) in enemy for r in ahead for f in (file - 1, file, file + 1) if 0 <= f < 8
            )
            total += not blocked
    return total


def game_metrics(pgn: str) -> Metrics | None:
    """
    Metrics of a game by its PGN. None — a game from its own position (a FEN header), without a result or without moves: it
    does not
    go into collections. Check is counted after each move, passed pawns — after each Black move (the largest
    number per game is taken), mate and stalemate — by the final position.
    """
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None or "FEN" in game.headers or game.headers.get("Result") not in ("1-0", "0-1", "1/2-1/2"):
        return None
    board = game.board()
    plies = checks = captures = streak = best_streak = promotions = most_passed = 0
    for move in game.mainline_moves():
        capture = board.is_capture(move)
        captures += capture
        streak = streak + 1 if capture else 0
        best_streak = max(best_streak, streak)
        promotions += move.promotion is not None
        board.push(move)
        plies += 1
        checks += board.is_check()
        if board.pawns and plies % 2 == 0:  # once per move: passed pawns change slowly, and the count is not cheap
            most_passed = max(most_passed, passed_pawns(board))
    if plies == 0:
        return None
    return Metrics(plies, game.headers["Result"] != "1/2-1/2", checks, captures, best_streak, promotions,
                   most_passed, board.is_stalemate(), board.is_checkmate(),
                   zlib.crc32(" ".join(m.uci() for m in board.move_stack).encode()))


def rank_collections(metrics: dict[int, Metrics], size: int = PER_COLLECTION) -> dict[str, list[tuple[int, int]]]:
    """
    Places in the collections: {collection: [(game id, metric), ...]}; on a tie — the smaller id. metrics — metrics by
    game id, size — how many games in a collection. The selection conditions are in the module description.
    """
    items = list(metrics.items())

    def top(candidates, key, value) -> list[tuple[int, int]]:
        """The first size games by the sort key; one and the same game (the archive has duplicates) is taken once."""
        chosen: list[tuple[int, int]] = []
        seen: set[int] = set()
        for gid, m in sorted(candidates, key=lambda item: (key(item[1]), item[0])):
            if m.signature in seen:
                continue
            seen.add(m.signature)
            chosen.append((gid, value(m)))
            if len(chosen) == size:
                break
        return chosen

    return {
        "shortest": top([i for i in items if i[1].checkmate], lambda m: m.plies, lambda m: m.plies),
        "checks": top(items, lambda m: -m.checks, lambda m: m.checks),
        "capture_streak": top(items, lambda m: -m.capture_streak, lambda m: m.capture_streak),
        "peaceful": top([i for i in items if i[1].plies >= MIN_PEACEFUL_PLIES],
                        lambda m: (m.captures, -m.plies), lambda m: m.captures),
        "promotions": top([i for i in items if i[1].promotions], lambda m: -m.promotions, lambda m: m.promotions),
        "pawn_wars": top(items, lambda m: -m.passed_pawns, lambda m: m.passed_pawns),
        "stalemates": top([i for i in items if i[1].stalemate], lambda m: -m.plies, lambda m: m.plies),
    }
