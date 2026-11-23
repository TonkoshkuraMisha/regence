# --- FILE: scripts/style_metrics.py ---
"""
The character of bots in the middlegame from calibration games (task B.5): is style visible beyond the opening book.

    python scripts/calibrate_bots.py --only morphy staunton --rounds 4 --pgn scripts/calibration_runs/style.pgn
    python scripts/style_metrics.py scripts/calibration_runs/style.pgn

Only the middlegame is counted - from MIDDLEGAME_FROM_PLY and while the board holds at least MIDDLEGAME_MIN_PIECES points of
pieces (without pawns). Metrics are per 100 player moves, without an engine, by material:
* sacrifices - after the move and the opponent's reply the player's material is lower than before the move by
  SACRIFICE_PAWNS or more and a move later it has not been won back (a capture with an immediate recapture is not a
  sacrifice). Without an engine a sacrifice looks like a blunder - so compare bots of about the same strength;
* trades - a capture of an equal-value piece (not a pawn) that the opponent at once answers by capturing on the same square;
* checks;
* king pressure - how many times the player's pieces attack the squares around the opponent's king (on average after a move);
* storm - pawn moves forward on the opponent's king flank (the king's file ±1), beyond one's own half of the board.

Expectation by character: romantics (La Bourdonnais, Anderssen, Morphy, Zukertort) - more sacrifices, checks and king pressure,
Staunton and Paulsen - more trades and fewer sacrifices. Compare players with each other at similar strength:
a strong bot more often gets a won position and attacks simply because it is stronger.
"""

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import chess
import chess.pgn

MIDDLEGAME_FROM_PLY = 16
MIDDLEGAME_MIN_PIECES = 26
SACRIFICE_PAWNS = 2

VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}


def material(board: chess.Board, color: chess.Color) -> int:
    """A side's material minus the opponent's, in pawns."""
    return sum(
        VALUES[piece.piece_type] * (1 if piece.color == color else -1) for piece in board.piece_map().values()
    )


def piece_material(board: chess.Board) -> int:
    """Pieces of both sides without pawns and kings - it shows that the game has reached the endgame."""
    return sum(VALUES[p.piece_type] for p in board.piece_map().values() if p.piece_type != chess.PAWN)


def king_zone_attacks(board: chess.Board, color: chess.Color) -> int:
    """How many times a side's pieces attack the opponent's king and the squares around it."""
    king = board.king(not color)
    if king is None:
        return 0
    zone = chess.SquareSet(chess.BB_KING_ATTACKS[king]) | chess.SquareSet.from_square(king)
    return sum(len(board.attackers(color, square)) for square in zone)


@dataclass
class PlayerStats:
    games: int = 0
    moves: int = 0
    sacrifices: int = 0
    trades: int = 0
    checks: int = 0
    king_pressure: int = 0
    storm: int = 0
    opponents: set[str] = field(default_factory=set)

    def per_100(self, value: int) -> float:
        """Recomputes the count of a feature occurrences per 100 middlegame moves."""
        return 100.0 * value / self.moves if self.moves else 0.0

    def row(self) -> dict[str, float]:
        """Formats a style-metrics table row for one participant."""
        return {
            "sacrifices": self.per_100(self.sacrifices),
            "trades": self.per_100(self.trades),
            "checks": self.per_100(self.checks),
            "king_pressure": self.king_pressure / self.moves if self.moves else 0.0,
            "storm": self.per_100(self.storm),
        }


def _is_storm(board: chess.Board, move: chess.Move, color: chess.Color) -> bool:
    """Checks whether a move is a pawn storm toward the opponent's king."""
    piece = board.piece_at(move.from_square)
    king = board.king(not color)
    if piece is None or piece.piece_type != chess.PAWN or king is None or board.is_capture(move):
        return False
    if abs(chess.square_file(move.to_square) - chess.square_file(king)) > 1:
        return False
    rank = chess.square_rank(move.to_square)
    return rank >= 4 if color == chess.WHITE else rank <= 3


def _is_trade(before: chess.Board, move: chess.Move, after: chess.Board, reply: chess.Move) -> bool:
    """A capture of a piece of equal value to which the opponent at once replies with a capture on the same square."""
    captured = before.piece_at(move.to_square)
    mover = before.piece_at(move.from_square)
    if captured is None or mover is None or captured.piece_type == chess.PAWN:
        return False
    if VALUES[captured.piece_type] != VALUES[mover.piece_type]:
        return False
    return reply.to_square == move.to_square and after.is_capture(reply)


def game_stats(game: chess.pgn.Game, from_ply: int = MIDDLEGAME_FROM_PLY) -> dict[chess.Color, PlayerStats]:
    """Metrics of one game for White and Black."""
    stats = {chess.WHITE: PlayerStats(games=1), chess.BLACK: PlayerStats(games=1)}
    board = game.board()
    moves = list(game.mainline_moves())
    # Positions before every ply and after the last: they show what became of the material after 2 and 4 plies.
    positions = [board.copy(stack=False)]
    for move in moves:
        board.push(move)
        positions.append(board.copy(stack=False))

    for i, move in enumerate(moves):
        before = positions[i]
        color = before.turn
        ply = before.ply()
        if ply < from_ply or piece_material(before) < MIDDLEGAME_MIN_PIECES:
            continue
        player = stats[color]
        player.moves += 1
        after = positions[i + 1]
        start = material(before, color)
        reply = positions[min(i + 2, len(moves))]
        later = positions[min(i + 4, len(moves))]
        if (material(reply, color) <= start - SACRIFICE_PAWNS and material(later, color) <= start - SACRIFICE_PAWNS
                and not after.is_checkmate()):
            player.sacrifices += 1
        if i + 1 < len(moves) and _is_trade(before, move, after, moves[i + 1]):
            player.trades += 1
        if after.is_check():
            player.checks += 1
        player.king_pressure += king_zone_attacks(after, color)
        if _is_storm(before, move, color):
            player.storm += 1
    return stats


def collect(path: Path, from_ply: int = MIDDLEGAME_FROM_PLY) -> dict[str, PlayerStats]:
    """Metrics over all games of a file, by player (White/Black headers)."""
    totals: dict[str, PlayerStats] = defaultdict(PlayerStats)
    with path.open(encoding="utf-8") as handle:
        while (game := chess.pgn.read_game(handle)) is not None:
            names = {chess.WHITE: game.headers.get("White", "?"), chess.BLACK: game.headers.get("Black", "?")}
            for color, stats in game_stats(game, from_ply).items():
                total = totals[names[color]]
                total.games += stats.games
                total.moves += stats.moves
                total.sacrifices += stats.sacrifices
                total.trades += stats.trades
                total.checks += stats.checks
                total.king_pressure += stats.king_pressure
                total.storm += stats.storm
                total.opponents.add(names[not color])
    return dict(totals)


def report(totals: dict[str, PlayerStats], with_anchors: bool = False) -> str:
    """Computes and formats the middlegame style metrics table from PGN games."""
    header = f"{'player':<28}{'games':>7}{'moves':>7}{'sacs':>8}{'trades':>9}{'checks':>7}{'press.':>7}{'storm':>7}"
    lines = [header, "-" * len(header)]
    for name in sorted(totals, key=lambda n: -totals[n].row()["sacrifices"]):
        if name.startswith("anchor:") and not with_anchors:
            continue
        stats = totals[name]
        row = stats.row()
        lines.append(
            f"{name:<28}{stats.games:>7}{stats.moves:>7}{row['sacrifices']:>8.1f}{row['trades']:>9.1f}"
            f"{row['checks']:>7.1f}{row['king_pressure']:>7.2f}{row['storm']:>7.1f}"
        )
    lines.append("sacs, trades, checks, storm - per 100 middlegame moves; press. - attacks on the king zone after a move")
    return "\n".join(lines)


def main() -> None:
    """CLI entry point for computing bot style metrics from a PGN file."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pgn", type=Path, help="PGN of calibration games (calibrate_bots.py --pgn)")
    parser.add_argument("--from-ply", type=int, default=MIDDLEGAME_FROM_PLY, help="Ply from which the middlegame starts")
    parser.add_argument("--anchors", action="store_true", help="Also show the Stockfish anchors (for comparison)")
    args = parser.parse_args()
    if not args.pgn.exists():
        raise SystemExit(f"File not found: {args.pgn}")
    print(report(collect(args.pgn, args.from_ply), args.anchors))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    main()
