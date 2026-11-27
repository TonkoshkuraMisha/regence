"""
Search for lesson positions in masters' games (data/pgns): a motif finds the rule, the engine confirms.

How it works: every game is walked move by move; a motif rule (registry RULES) looks at the position and the master's move
played and selects "candidates". Each candidate is checked by Stockfish: the move played must be the best, and the
second-best move must be weaker by at least --margin cp (otherwise the "find the move" question can be guessed), and the
evaluation for the side to move - not below --min-score. Result: JSON with a list of {fen, move, san, game, rule, scores};
a lesson is built from them (a human writes the text, the engine vouches for the move). Not for CI: needs Stockfish.

Rules (by the RULES registry):
  interference - a piece steps between the opponent's defender and the defended piece; the defence breaks, leaving it bare;
  rook_lift    - a rook rises from the first rank to the third toward the opponent's king;
  pawn_storm   - a pawn storm (g/h) at the opponent's king with castling to opposite sides;
  blockade     - a piece blocks the opponent's passed pawn;
  quiet_move   - a quiet move (not a capture or a check) that is much better than the rest;
  overload     - the opponent has an overloaded piece (a mentor detector), the move attacks it or one of its targets;
  remove_defender - capture of the sole defender of an opponent piece, after which it is left undefended;
  knight_outpost - a knight settles on a central pawn-guarded square that no opponent pawn can attack (S3.8);
  minor_exchange - a minor piece trades itself for a defended opponent minor piece (choice of exchange, S4.10).

    python -m scripts.dev.mine_lesson_positions --rule interference --limit 12 --out interference.json
"""

import argparse
import glob
import json
import os
import pathlib

import chess
import chess.engine
import chess.pgn

from src.services.bots.base import resolve_stockfish_path
from src.services.mentor_service import detect_motifs

ROOT = pathlib.Path(__file__).resolve().parents[2]
# LESSON_PGN_ROOT points the search at another folder of PGN files (for example the owner's game collection).
PGN_GLOB = str(pathlib.Path(os.environ.get("LESSON_PGN_ROOT") or ROOT / "data" / "pgns") / "**" / "*.pgn")
MATE_SCORE = 100_000
SLIDERS = (chess.BISHOP, chess.ROOK, chess.QUEEN)


def relative_rank(square: chess.Square, colour: chess.Color) -> int:
    """Rank from the colour's point of view: 0 - own first, 7 - last."""
    rank = chess.square_rank(square)
    return rank if colour == chess.WHITE else 7 - rank


def rule_interference(board: chess.Board, move: chess.Move) -> bool:
    """The move steps onto the line between a slider defender and the opponent's piece it defends, leaving it undefended."""
    mover, enemy = board.turn, not board.turn
    if board.is_capture(move):
        return False
    after = board.copy(stack=False)
    after.push(move)
    for target in chess.SquareSet(board.occupied_co[enemy]):
        piece = board.piece_at(target)
        if piece is None or piece.piece_type == chess.KING:
            continue
        defenders = board.attackers(enemy, target)
        for guard in defenders:
            guard_piece = board.piece_at(guard)
            if guard_piece is None or guard_piece.piece_type not in SLIDERS:
                continue
            between = chess.SquareSet(chess.between(guard, target))
            if (move.to_square in between and len(defenders) == 1
                    and after.attackers(mover, target) and not after.attackers(enemy, target)):
                return True
    return False


def rule_rook_lift(board: chess.Board, move: chess.Move) -> bool:
    """A rook goes from the first rank to the third toward the opponent's king (the king is on the side of the lift)."""
    mover, enemy = board.turn, not board.turn
    piece = board.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.ROOK or board.is_capture(move) or board.fullmove_number < 9:
        return False
    if relative_rank(move.from_square, mover) != 0 or relative_rank(move.to_square, mover) != 2:
        return False
    king_file = chess.square_file(board.king(enemy))
    file_ = chess.square_file(move.to_square)
    return (king_file >= 5 and file_ >= 3) or (king_file <= 2 and file_ <= 4)


def rule_pawn_storm(board: chess.Board, move: chess.Move) -> bool:
    """A g/h pawn goes toward the opponent's king, castling to opposite sides, the mover has already castled."""
    mover, enemy = board.turn, not board.turn
    piece = board.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.PAWN or board.is_capture(move):
        return False
    file_, rank = chess.square_file(move.to_square), relative_rank(move.to_square, mover)
    own_king, enemy_king = board.king(mover), board.king(enemy)
    opposite = (chess.square_file(own_king) <= 2) != (chess.square_file(enemy_king) <= 2)
    return (opposite and rank in (3, 4) and board.fullmove_number >= 10
            and abs(file_ - chess.square_file(enemy_king)) <= 1 and relative_rank(enemy_king, enemy) == 0)


def rule_blockade(board: chess.Board, move: chess.Move) -> bool:
    """A piece (not a king or a pawn) stands in front of an opponent's passed pawn that has advanced far."""
    mover, enemy = board.turn, not board.turn
    piece = board.piece_at(move.from_square)
    if piece is None or piece.piece_type in (chess.KING, chess.PAWN) or board.is_capture(move):
        return False
    step = 8 if enemy == chess.WHITE else -8
    pawn_sq = move.to_square - step
    if not 0 <= pawn_sq < 64:
        return False
    pawn = board.piece_at(pawn_sq)
    if pawn is None or pawn.piece_type != chess.PAWN or pawn.color != enemy or relative_rank(pawn_sq, enemy) < 3:
        return False
    file_ = chess.square_file(pawn_sq)
    for our in board.pieces(chess.PAWN, mover):
        ahead = (chess.square_rank(our) - chess.square_rank(pawn_sq)) * (1 if enemy == chess.WHITE else -1) > 0
        if ahead and abs(chess.square_file(our) - file_) <= 1:
            return False
    return True


def rule_quiet_move(board: chess.Board, move: chess.Move) -> bool:
    """A quiet move: not a capture, not a check, not a promotion and not a king move."""
    piece = board.piece_at(move.from_square)
    return (piece is not None and piece.piece_type != chess.KING and not board.is_capture(move)
            and not board.gives_check(move) and move.promotion is None and board.fullmove_number >= 12)


def rule_overload(board: chess.Board, move: chess.Move) -> bool:
    """The opponent has an overloaded piece (mentor motif ``overloaded``), and the move captures it or one of its targets."""
    if not board.is_capture(move):
        return False
    return any(motif.code == "overloaded" and motif.color == board.turn
               and (move.to_square == motif.square or move.to_square in motif.targets)
               for motif in detect_motifs(board))


def rule_remove_defender(board: chess.Board, move: chess.Move) -> bool:
    """The move captures the only defender of another opponent piece; that piece is left attacked and undefended."""
    mover, enemy = board.turn, not board.turn
    if not board.is_capture(move):
        return False
    captured = move.to_square
    after = board.copy(stack=False)
    after.push(move)
    for target in chess.SquareSet(board.occupied_co[enemy]):
        piece = board.piece_at(target)
        if target == captured or piece is None or piece.piece_type in (chess.KING, chess.PAWN):
            continue
        if (list(board.attackers(enemy, target)) == [captured] and after.attackers(mover, target)
                and not after.attackers(enemy, target)):
            return True
    return False


OUTPOST_FILES = range(2, 6)  # files c-f: a knight there reaches both wings and the centre
OUTPOST_RANKS = range(3, 6)  # the mover's 4th-6th rank: in the opponent's half or on its border
MIDDLEGAME_FROM_MOVE = 12  # earlier moves are opening theory, not a plan
MINOR_PIECES = (chess.KNIGHT, chess.BISHOP)


def rule_knight_outpost(board: chess.Board, move: chess.Move) -> bool:
    """A knight goes (not capturing) to a central square of the 4th-6th rank that is guarded by its own pawn and that no
    opponent pawn can ever attack (no opponent pawn on a neighbouring file further up the board)."""
    mover, enemy = board.turn, not board.turn
    piece = board.piece_at(move.from_square)
    if (piece is None or piece.piece_type != chess.KNIGHT or board.is_capture(move)
            or board.fullmove_number < MIDDLEGAME_FROM_MOVE):
        return False
    square = move.to_square
    file_, rank = chess.square_file(square), relative_rank(square, mover)
    if file_ not in OUTPOST_FILES or rank not in OUTPOST_RANKS:
        return False
    if not any(board.piece_at(s) == chess.Piece(chess.PAWN, mover) for s in board.attackers(mover, square)):
        return False
    return not any(abs(chess.square_file(p) - file_) == 1 and relative_rank(p, mover) > rank
                   for p in board.pieces(chess.PAWN, enemy))


def rule_minor_exchange(board: chess.Board, move: chess.Move) -> bool:
    """A minor piece takes a defended minor piece (an exchange, not a win of material): the choice of which piece to trade."""
    mover = board.turn
    piece, target = board.piece_at(move.from_square), board.piece_at(move.to_square)
    return (piece is not None and target is not None and piece.piece_type in MINOR_PIECES
            and target.piece_type in MINOR_PIECES and target.color != mover
            and bool(board.attackers(not mover, move.to_square)) and not board.gives_check(move)
            and board.fullmove_number >= MIDDLEGAME_FROM_MOVE)


RULES = {"interference": rule_interference, "rook_lift": rule_rook_lift, "pawn_storm": rule_pawn_storm,
         "blockade": rule_blockade, "quiet_move": rule_quiet_move, "overload": rule_overload,
         "remove_defender": rule_remove_defender, "knight_outpost": rule_knight_outpost,
         "minor_exchange": rule_minor_exchange}


def candidates(rule_name: str):
    """Candidate positions by a rule: (fen before the move, the move, the game description)."""
    rule = RULES[rule_name]
    seen: set[str] = set()
    for path in sorted(glob.glob(PGN_GLOB, recursive=True)):
        with open(path, encoding="utf-8", errors="ignore") as handle:
            while True:
                try:
                    game = chess.pgn.read_game(handle)
                except Exception:  # noqa: BLE001 - a broken PGN record is skipped, the search goes on
                    break
                if game is None:
                    break
                node = game
                while node.variations:
                    nxt = node.variation(0)
                    board = node.board()
                    if rule(board, nxt.move):
                        key = board.board_fen()
                        if key not in seen:
                            seen.add(key)
                            info = f"{game.headers.get('White')} — {game.headers.get('Black')}, {game.headers.get('Date')}"
                            yield board.fen(), nxt.move, info
                    node = nxt


def main() -> None:
    """Checks the candidates with the engine and saves the confirmed ones."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rule", required=True, choices=sorted(RULES))
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--time", type=float, default=0.8)
    parser.add_argument("--margin", type=int, default=150)
    parser.add_argument("--min-score", type=int, default=120)
    parser.add_argument("--max-candidates", type=int, default=600)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args()
    engine = chess.engine.SimpleEngine.popen_uci(resolve_stockfish_path())
    found: list[dict] = []
    checked = 0
    try:
        for fen, move, game in candidates(args.rule):
            checked += 1
            if checked > args.max_candidates or len(found) >= args.limit:
                break
            board = chess.Board(fen)
            infos = engine.analyse(board, chess.engine.Limit(time=args.time), multipv=2)
            if len(infos) < 2 or infos[0]["pv"][0] != move:
                continue
            scores = [i["score"].pov(board.turn).score(mate_score=MATE_SCORE) for i in infos]
            if scores[0] >= args.min_score and scores[0] - scores[1] >= args.margin:
                item = {"fen": fen, "move": move.uci(), "san": board.san(move), "game": game, "rule": args.rule,
                        "scores": scores}
                found.append(item)
                print(item, flush=True)
    finally:
        engine.quit()
    args.out.write_text(json.dumps(found, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"checked {checked}, found {len(found)} -> {args.out}")


if __name__ == "__main__":
    main()
