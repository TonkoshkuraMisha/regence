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
  minor_exchange - a minor piece trades itself for a defended opponent minor piece (choice of exchange, S4.10);
  restriction - a quiet pawn move that takes many legal moves away from the opponent (S4.8);
  worst_piece - the least mobile piece goes to a square where it has many more moves (S4.9);
  prophylaxis - a quiet move that removes the opponent's material threat in advance (S4.9);
  critical - a tense position with many captures for both sides; the engine margin finds the only good move (S5.1);
  quiet_over_forcing - a quiet move chosen while captures and checks were available (creative thinking, C5.1);
  greedy_refuted - a piece could be taken, the master did something else: the capture is refuted (C4.1);
  development_lead - the opponent's king is in the centre and his minor pieces at home (S5.2);
  greek_gift - Bxh7+ / ...Bxh2+ against the castled king (S5.3);
  bishop_takes_g7 - a bishop takes the g-pawn in front of the castled king (S5.3).

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
    """A minor piece takes a defended minor piece (an exchange, not a win of material): the choice of which piece to trade.
    A recapture on the square the opponent has just captured on is not a choice and is skipped (needs the move stack)."""
    mover = board.turn
    piece, target = board.piece_at(move.from_square), board.piece_at(move.to_square)
    if board.move_stack and board.peek().to_square == move.to_square:
        return False
    return (piece is not None and target is not None and piece.piece_type in MINOR_PIECES
            and target.piece_type in MINOR_PIECES and target.color != mover
            and bool(board.attackers(not mover, move.to_square)) and not board.gives_check(move)
            and board.fullmove_number >= MIDDLEGAME_FROM_MOVE)


RESTRICT_MIN_DROP = 6  # the opponent loses at least this many legal moves...
RESTRICT_MAX_SHARE = 0.75  # ...and keeps no more than this share of them: a real squeeze, not a lost check
IMPROVE_MIN_GAIN = 5  # the worst piece gains at least this many squares: from passive to active
BOXED_BEFORE = 3  # a piece that had at least this many moves...
BOXED_AFTER = 1  # ...and keeps at most this many after the pawn move is boxed in
PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
THREAT_MIN_GAIN = 2  # a capture that wins at least two pawns of material is a threat worth preventing
IMPROVABLE = (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)


def _is_quiet(board: chess.Board, move: chess.Move) -> bool:
    """Not a capture, not a check, not a promotion, not castling, in the middlegame, and the mover is not in check."""
    return (not board.is_capture(move) and not board.gives_check(move) and move.promotion is None
            and not board.is_castling(move) and not board.is_check() and board.fullmove_number >= MIDDLEGAME_FROM_MOVE)


def _after_pass(board: chess.Board) -> chess.Board:
    """The position with the side to move skipping its turn (a null move): what the opponent could do "if we pass"."""
    passed = board.copy(stack=False)
    passed.push(chess.Move.null())
    return passed


def _piece_mobility(board: chess.Board, square: chess.Square) -> int:
    """Legal moves of the piece on the square for the side to move."""
    return sum(1 for m in board.legal_moves if m.from_square == square)


def _material_threats(board: chess.Board) -> set[chess.Square]:
    """Squares where the side to move wins >= THREAT_MIN_GAIN by a capture: the captured value minus the capturer's value
    if the target is defended (a one-step exchange estimate, enough to pick candidates for the engine)."""
    threats = set()
    for move in board.legal_moves:
        target = board.piece_at(move.to_square)
        attacker = board.piece_at(move.from_square)
        if target is None or attacker is None:
            continue
        defended = bool(board.attackers(not board.turn, move.to_square))
        gain = PIECE_VALUES[target.piece_type] - (PIECE_VALUES[attacker.piece_type] if defended else 0)
        if gain >= THREAT_MIN_GAIN:
            threats.add(move.to_square)
    return threats


def rule_restriction(board: chess.Board, move: chess.Move) -> bool:
    """A quiet move that takes squares away (S4.8): compared with passing, either a pawn move leaves the opponent
    RESTRICT_MIN_DROP fewer legal moves and no more than RESTRICT_MAX_SHARE of them, or any piece or pawn move boxes one of
    his pieces in (domination) - it had at least BOXED_BEFORE moves and keeps at most BOXED_AFTER."""
    piece = board.piece_at(move.from_square)
    if piece is None or piece.piece_type == chess.KING or not _is_quiet(board, move):
        return False
    passed = _after_pass(board)
    after = board.copy(stack=False)
    after.push(move)
    before, left = passed.legal_moves.count(), after.legal_moves.count()
    if piece.piece_type == chess.PAWN and before - left >= RESTRICT_MIN_DROP and left <= before * RESTRICT_MAX_SHARE:
        return True
    enemy = [sq for sq in chess.SquareSet(after.occupied_co[after.turn]) if after.piece_type_at(sq) in IMPROVABLE]
    return any(_piece_mobility(passed, sq) >= BOXED_BEFORE and _piece_mobility(after, sq) <= BOXED_AFTER for sq in enemy)


def rule_worst_piece(board: chess.Board, move: chess.Move) -> bool:
    """A quiet move of the mover's least mobile piece (knight, bishop, rook or queen) after which it has IMPROVE_MIN_GAIN
    more legal moves (counted as if the opponent passed): the worst piece goes to a better square (S4.9)."""
    piece = board.piece_at(move.from_square)
    if piece is None or piece.piece_type not in IMPROVABLE or not _is_quiet(board, move):
        return False
    own = [sq for sq in chess.SquareSet(board.occupied_co[board.turn]) if board.piece_type_at(sq) in IMPROVABLE]
    mobility = {sq: _piece_mobility(board, sq) for sq in own}
    if mobility[move.from_square] > min(mobility.values()):
        return False
    after = board.copy(stack=False)
    after.push(move)
    if after.is_check():
        return False
    return _piece_mobility(_after_pass(after), move.to_square) - mobility[move.from_square] >= IMPROVE_MIN_GAIN


def rule_prophylaxis(board: chess.Board, move: chess.Move) -> bool:
    """A quiet move that removes the opponent's material threat (seen by a null move) without moving the threatened piece
    away: a square is covered or a line is closed in advance (S4.9)."""
    if not _is_quiet(board, move):
        return False
    threats = _material_threats(_after_pass(board))
    if not threats or move.from_square in threats:
        return False
    after = board.copy(stack=False)
    after.push(move)
    return not _material_threats(after)


TENSION_OWN_CAPTURES = 4  # captures for the side to move...
TENSION_ENEMY_CAPTURES = 3  # ...and for the opponent if we passed: pieces in contact, the position is about to change
FORCING_ALTERNATIVES = 2  # captures and checks available besides the quiet move


def _forcing_moves(board: chess.Board) -> int:
    """Legal captures and checks of the side to move."""
    return sum(1 for m in board.legal_moves if board.is_capture(m) or board.gives_check(m))


def rule_critical(board: chess.Board, move: chess.Move) -> bool:
    """A tense middlegame position (S5.1): many captures for both sides, the mover not in check. Which move keeps the
    advantage is decided by the engine (a wide --margin): the other moves throw it away."""
    if board.is_check() or board.fullmove_number < MIDDLEGAME_FROM_MOVE:
        return False
    own = sum(1 for m in board.legal_moves if board.is_capture(m))
    passed = _after_pass(board)
    return own >= TENSION_OWN_CAPTURES and sum(1 for m in passed.legal_moves if passed.is_capture(m)) >= TENSION_ENEMY_CAPTURES


def rule_quiet_over_forcing(board: chess.Board, move: chess.Move) -> bool:
    """A quiet move played while captures and checks were available (C5.1): the creative move is not the obvious one."""
    return _is_quiet(board, move) and _forcing_moves(board) >= FORCING_ALTERNATIVES


GREEDY_MIN_VALUE = 3  # the tempting capture takes at least a minor piece


def rule_greedy_refuted(board: chess.Board, move: chess.Move) -> bool:
    """A piece (worth GREEDY_MIN_VALUE or more) can be captured, yet the master played something else (C4.1): with a
    wide engine --margin the capture is refuted by the opponent's reply, and calculating that reply is the lesson."""
    if board.is_check() or board.fullmove_number < MIDDLEGAME_FROM_MOVE or board.is_capture(move):
        return False
    return any(board.is_capture(m) and (target := board.piece_at(m.to_square)) is not None
               and PIECE_VALUES[target.piece_type] >= GREEDY_MIN_VALUE for m in board.legal_moves)


MINOR_HOME = {chess.WHITE: (chess.B1, chess.C1, chess.F1, chess.G1), chess.BLACK: (chess.B8, chess.C8, chess.F8, chess.G8)}
KING_HOME = {chess.WHITE: chess.E1, chess.BLACK: chess.E8}
DEVELOPMENT_LEAD = 2  # the opponent has at least this many more minor pieces still at home
OPENING_PHASE = range(8, 26)  # a lead in development matters while the opening turns into the middlegame


def _undeveloped(board: chess.Board, colour: chess.Color) -> int:
    """Knights and bishops of the colour still standing on their home squares."""
    return sum(1 for sq in MINOR_HOME[colour]
               if (p := board.piece_at(sq)) is not None and p.color == colour and p.piece_type in MINOR_PIECES)


def rule_development_lead(board: chess.Board, move: chess.Move) -> bool:
    """The opponent's king is still on its home square and he has DEVELOPMENT_LEAD more undeveloped minor pieces (S5.2):
    with a wide engine --margin the energetic move that uses the lead is the only good one."""
    mover, enemy = board.turn, not board.turn
    return (board.fullmove_number in OPENING_PHASE and not board.is_check()
            and board.king(enemy) == KING_HOME[enemy]
            and _undeveloped(board, enemy) - _undeveloped(board, mover) >= DEVELOPMENT_LEAD)


def rule_greek_gift(board: chess.Board, move: chess.Move) -> bool:
    """A bishop takes the h-pawn next to the castled king with check (Bxh7+ / ...Bxh2+, S5.3)."""
    mover, enemy = board.turn, not board.turn
    piece = board.piece_at(move.from_square)
    target = chess.H7 if mover == chess.WHITE else chess.H2
    king_square = chess.G8 if mover == chess.WHITE else chess.G1
    return (piece is not None and piece.piece_type == chess.BISHOP and move.to_square == target
            and board.piece_type_at(target) == chess.PAWN and board.king(enemy) == king_square and board.gives_check(move))


def rule_bishop_takes_g7(board: chess.Board, move: chess.Move) -> bool:
    """A bishop takes the g-pawn in front of the castled king (Bxg7 / ...Bxg2) - the second bishop of the double bishop
    sacrifice or a lone breach of the king's cover (S5.3)."""
    mover, enemy = board.turn, not board.turn
    piece = board.piece_at(move.from_square)
    target = chess.G7 if mover == chess.WHITE else chess.G2
    king_squares = (chess.G8, chess.H8, chess.F8) if mover == chess.WHITE else (chess.G1, chess.H1, chess.F1)
    return (piece is not None and piece.piece_type == chess.BISHOP and move.to_square == target
            and board.piece_type_at(target) == chess.PAWN and board.king(enemy) in king_squares
            and board.fullmove_number >= MIDDLEGAME_FROM_MOVE)


RULES = {"interference": rule_interference, "rook_lift": rule_rook_lift, "pawn_storm": rule_pawn_storm,
         "blockade": rule_blockade, "quiet_move": rule_quiet_move, "overload": rule_overload,
         "remove_defender": rule_remove_defender, "knight_outpost": rule_knight_outpost,
         "minor_exchange": rule_minor_exchange, "restriction": rule_restriction, "worst_piece": rule_worst_piece,
         "prophylaxis": rule_prophylaxis, "critical": rule_critical, "quiet_over_forcing": rule_quiet_over_forcing,
         "greedy_refuted": rule_greedy_refuted, "development_lead": rule_development_lead,
         "greek_gift": rule_greek_gift, "bishop_takes_g7": rule_bishop_takes_g7}


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
    # A strategy lesson needs a calm position: a best move worth +500 is a tactic, not a positional choice.
    parser.add_argument("--max-score", type=int, default=MATE_SCORE, help="upper bound of the best move's evaluation")
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
            if args.min_score <= scores[0] <= args.max_score and scores[0] - scores[1] >= args.margin:
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
