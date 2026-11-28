"""
Build the "Plan in this position" set (task 27.9): positions from masters' games where a plan of several moves was played.

What a question is: a position, three plans named by a category and their concrete first move in this position
("Queenside pawns: b4", "Reroute a knight: Nf1"). One of them is the plan the master played; the other two are other
categories with a legal first move here. Every first move is a quiet move (no capture, no check): a plan, not a tactic.

How a plan is recognised (pure rules, tests/test_position_plans.py):
  * categorise() puts a quiet move into one PLANS category by a fixed priority (a passed-pawn push is a passed-pawn plan
    even on the b-file);
  * the master's plan is confirmed when, among his next WINDOW moves, at least PLANS[code].min_moves belong to the same
    category (a queenside attack is b4 and b5, a manoeuvre is two moves of one knight ending on a pawn-guarded square in the
    opponent's half, a pawn break is the break itself).

How the engine vouches (Stockfish, so not for CI): the master's first move is no worse than the engine's best by more than
BEST_TOLERANCE cp; for each wrong category its best first move (all its candidates are analysed) is weaker than the master's
move by at least --margin cp. The position must be calm (|evaluation| <= --max-eval) - a question about a plan, not about a
winning combination. The evaluations are stored with the question and shown after the answer.

Source: PGN files under LESSON_PGN_ROOT (or data/pgns), e.g. the archive exported from the games table. Output:
frontend/src/content/positionPlans.json (read by frontend/src/components/trainers/PositionPlanQuiz.tsx); the texts of the
categories are i18n keys positionPlans.<code> (en/uk), the file itself holds no player-facing text.

    python -m scripts.dev.build_position_plans --limit 60 --time 0.5 --stride 40   # mine (fast, noisy)
    python -m scripts.dev.build_position_plans --verify --time 3.0                 # re-check on a longer search
"""

import argparse
import glob
import json
import os
import pathlib
from dataclasses import dataclass

import chess
import chess.engine
import chess.pgn

from src.services.bots.base import resolve_stockfish_path

ROOT = pathlib.Path(__file__).resolve().parents[2]
PGN_GLOB = str(pathlib.Path(os.environ.get("LESSON_PGN_ROOT") or ROOT / "data" / "pgns") / "**" / "*.pgn")
OUT = ROOT / "frontend" / "src" / "content" / "positionPlans.json"
MATE_SCORE = 100_000
WINDOW = 5  # the master's own moves looked at to recognise a plan (ten plies)
CONTINUATION_PLIES = 12  # game moves stored after the position, played out on the board after the answer
FIRST_MOVE = 12  # earlier positions are opening theory: the plan belongs to the middlegame
WRONG_OPTIONS = 2  # three options in a question
BEST_TOLERANCE = 30  # the master's move may be this much (cp) below the engine's best and still be "the" plan
QUEENSIDE = range(0, 3)  # files a-c
KINGSIDE = range(5, 8)  # files f-h
STORM_FILES = range(6, 8)  # files g-h: pawns that storm a castled king
BREAK_FILES = range(2, 6)  # files c-f: central breaks
ADVANCE_RANK = 3  # a storm or queenside push reaches the mover's fourth rank (g4, b4): h3, g3 or a3 attack nothing
HEAVY = (chess.ROOK, chess.QUEEN)
MARCH_CHECKS = 1  # a marching king may answer one check on the way; more checks mean it is being chased, not marching


@dataclass(frozen=True)
class Plan:
    """A plan category: how many of the master's WINDOW moves must belong to it to count as a plan."""

    min_moves: int


PLANS: dict[str, Plan] = {
    "passed_pawn": Plan(2),  # push the passed pawn
    "central_break": Plan(1),  # a pawn break in the centre: the move itself attacks an opponent pawn
    "pawn_storm": Plan(2),  # g/h pawns against the opponent's king on the kingside
    "queenside_pawns": Plan(2),  # queenside pawns against a queenside pawn majority or chain
    "knight_manoeuvre": Plan(2),  # one knight, several quiet moves, ends on a pawn-guarded square in the opponent's half
    "rook_file": Plan(1),  # a rook goes to a file without own pawns, then doubles on it or advances along it
    "king_march": Plan(3),  # the king walks forward in an endgame without queens
}


def relative_rank(square: chess.Square, colour: chess.Color) -> int:
    """Rank 0..7 from the mover's side."""
    rank = chess.square_rank(square)
    return rank if colour == chess.WHITE else 7 - rank


def is_quiet(board: chess.Board, move: chess.Move) -> bool:
    """Not a capture, a check or a promotion: the first move of a plan."""
    return not (board.is_capture(move) or board.gives_check(move) or move.promotion)


def is_passed(board: chess.Board, square: chess.Square, colour: chess.Color) -> bool:
    """No opponent pawn in front of the pawn on its own and the adjacent files."""
    file, rank = chess.square_file(square), chess.square_rank(square)
    for enemy in board.pieces(chess.PAWN, not colour):
        enemy_file, enemy_rank = chess.square_file(enemy), chess.square_rank(enemy)
        ahead = enemy_rank > rank if colour == chess.WHITE else enemy_rank < rank
        if abs(enemy_file - file) <= 1 and ahead:
            return False
    return True


def _attacks_pawn(board: chess.Board, move: chess.Move) -> bool:
    """After the pawn push the pawn attacks an opponent pawn: a break that opens a file."""
    after = board.copy(stack=False)
    after.push(move)
    return any(after.piece_type_at(sq) == chess.PAWN and after.color_at(sq) != board.turn
               for sq in after.attacks(move.to_square))


def _pawn_guarded(board: chess.Board, square: chess.Square, colour: chess.Color) -> bool:
    """The square is protected by a pawn of the colour."""
    return any(board.piece_type_at(sq) == chess.PAWN for sq in board.attackers(colour, square))


def _no_queens(board: chess.Board) -> bool:
    return not board.pieces(chess.QUEEN, chess.WHITE) and not board.pieces(chess.QUEEN, chess.BLACK)


def categorise(board: chess.Board, move: chess.Move) -> str | None:
    """The plan category a quiet move starts, by the PLANS priority; None for a move that is no plan's first step."""
    if not is_quiet(board, move):
        return None
    colour = board.turn
    piece = board.piece_type_at(move.from_square)
    to_file = chess.square_file(move.to_square)
    if piece == chess.PAWN:
        if is_passed(board, move.from_square, colour):
            return "passed_pawn"
        if to_file in BREAK_FILES and _attacks_pawn(board, move):
            return "central_break"
        enemy_king = board.king(not colour)
        advanced = relative_rank(move.to_square, colour) >= ADVANCE_RANK
        if to_file in STORM_FILES and advanced and enemy_king is not None \
                and chess.square_file(enemy_king) in KINGSIDE and not _no_queens(board):
            return "pawn_storm"
        if to_file in QUEENSIDE and advanced:
            return "queenside_pawns"
        return None
    if piece == chess.KNIGHT:
        return "knight_manoeuvre"
    if piece == chess.ROOK:
        own_pawns = [sq for sq in board.pieces(chess.PAWN, colour) if chess.square_file(sq) == to_file]
        return "rook_file" if not own_pawns and chess.square_file(move.from_square) != to_file else None
    if piece == chess.KING and _no_queens(board):
        return "king_march"
    return None


def _minority(board: chess.Board, colour: chess.Color) -> bool:
    """The mover has fewer pawns on files a-c than the opponent, or as many: a pawn minority or a chain to attack."""
    def count(side: chess.Color) -> int:
        return sum(1 for sq in board.pieces(chess.PAWN, side) if chess.square_file(sq) in QUEENSIDE)
    return 0 < count(colour) <= count(not colour)


def applies(board: chess.Board, code: str) -> bool:
    """Whether a category makes sense as a plan in this position at all (a wrong option must still be a real plan)."""
    if code == "queenside_pawns":
        return _minority(board, board.turn)
    return True


def master_plan(board: chess.Board, moves: list[chess.Move]) -> str | None:
    """The plan the master played from this position: moves are the game's next plies (the mover's are even indexes)."""
    if not moves:
        return None
    code = categorise(board, moves[0])
    if code is None or not applies(board, code):
        return None
    colour = board.turn
    work = board.copy(stack=False)
    own: list[tuple[chess.Board, chess.Move]] = []
    for ply, move in enumerate(moves[:2 * WINDOW]):
        if ply % 2 == 0:
            own.append((work.copy(stack=False), move))
        work.push(move)
    same = [(b, m) for b, m in own if categorise(b, m) == code]
    if len(same) < PLANS[code].min_moves:
        return None
    if code == "knight_manoeuvre":
        knight = moves[0].to_square
        route = [moves[0]]
        for _, m in same[1:]:
            if m.from_square == knight:
                route.append(m)
                knight = m.to_square
        end = route[-1].to_square
        return code if len(route) >= 2 and relative_rank(end, colour) >= 4 and _pawn_guarded(work, end, colour) else None
    if code == "queenside_pawns":
        return code if all(chess.square_file(m.to_square) in QUEENSIDE for _, m in same) else None
    if code == "king_march":
        return code if _king_marches(colour, same) else None
    if code == "rook_file":
        file = chess.square_file(moves[0].to_square)
        follow = [m for b, m in own[1:] if b.piece_type_at(m.from_square) in HEAVY and chess.square_file(m.to_square) == file]
        return code if follow else None
    return code


def _king_marches(colour: chess.Color, steps: list[tuple[chess.Board, chess.Move]]) -> bool:
    """A real march: at most MARCH_CHECKS steps answer a check, no square is visited twice, the king ends further forward.

    Without this a king that shuffles in a repetition or runs from a series of checks would count as a plan."""
    if sum(1 for b, _ in steps if b.is_check()) > MARCH_CHECKS:
        return False
    squares = [steps[0][1].from_square, *(m.to_square for _, m in steps)]
    if len(set(squares)) != len(squares):
        return False
    return relative_rank(squares[-1], colour) > relative_rank(squares[0], colour)


def surname(name: str) -> str:
    """'Steinitz, Wilhelm' -> 'Steinitz': the question names the game by surnames, as the lessons do."""
    return name.split(",")[0].strip() or "?"


def refilter(items: list[dict]) -> list[dict]:
    """Questions whose stored continuation still shows the stored plan under the current rules (no engine needed)."""
    kept = []
    for item in items:
        board = chess.Board(item["fen"])
        moves = [chess.Move.from_uci(u) for u in item["continuation"]]
        if master_plan(board, moves) == item["options"][0]["plan"]:
            kept.append({**item, "white": surname(item["white"]), "black": surname(item["black"])})
    return kept


def first_moves(board: chess.Board) -> dict[str, list[chess.Move]]:
    """Legal quiet first moves of every applicable category in the position."""
    found: dict[str, list[chess.Move]] = {}
    for move in board.legal_moves:
        code = categorise(board, move)
        if code is not None and applies(board, code):
            found.setdefault(code, []).append(move)
    return found


def _score(info: chess.engine.InfoDict, colour: chess.Color) -> int:
    return info["score"].pov(colour).score(mate_score=MATE_SCORE)


def check(engine: chess.engine.SimpleEngine, board: chess.Board, master: chess.Move, code: str, args) -> dict | None:
    """Engine check of one candidate: the question's options with their evaluations, or None."""
    colour = board.turn
    best = engine.analyse(board, chess.engine.Limit(time=args.time))
    best_score = _score(best, colour)
    if abs(best_score) > args.max_eval:
        return None
    by_code = first_moves(board)
    roots = [m for moves in by_code.values() for m in moves]
    infos = engine.analyse(board, chess.engine.Limit(time=args.time), multipv=len(roots), root_moves=roots)
    scores = {info["pv"][0]: _score(info, colour) for info in infos if info.get("pv")}
    if master not in scores or scores[master] < best_score - BEST_TOLERANCE:
        return None
    wrong = []
    for other, moves in by_code.items():
        rated = [(scores[m], m) for m in moves if m in scores]
        if other == code or not rated:
            continue
        top_score, top_move = max(rated, key=lambda pair: pair[0])
        if scores[master] - top_score >= args.margin:
            wrong.append((top_score, other, top_move))
    if len(wrong) < WRONG_OPTIONS:
        return None
    # The strongest wrong plans: the question is harder and the engine margin is still at least --margin.
    wrong.sort(key=lambda item: item[0], reverse=True)
    options = [{"plan": code, "move": master.uci(), "score": scores[master]}]
    options += [{"plan": other, "move": move.uci(), "score": score} for score, other, move in wrong[:WRONG_OPTIONS]]
    return {"options": options}


def candidates(done: set[int], stride: int):
    """(game number, board, master's move, the next plies, plan, headers) where the master's plan is recognised.

    done - numbers of games that already gave a question: at most one question per game, for variety;
    stride - only every stride-th game is read, so that a sorted archive gives masters of all eras."""
    seen: set[str] = set()
    number = 0
    for path in sorted(glob.glob(PGN_GLOB, recursive=True)):
        with open(path, encoding="utf-8", errors="ignore") as handle:
            while True:
                number += 1
                if number % stride:
                    if not chess.pgn.skip_game(handle):  # a skipped game is not parsed: the archive is read fast
                        break
                    continue
                try:
                    game = chess.pgn.read_game(handle)
                except Exception:  # noqa: BLE001 - a broken PGN record is skipped, the search goes on
                    break
                if game is None:
                    break
                moves = list(game.mainline_moves())
                board = game.board()
                for ply, move in enumerate(moves):
                    if number in done:
                        break
                    if board.fullmove_number >= FIRST_MOVE and not board.is_check():
                        rest = moves[ply:ply + CONTINUATION_PLIES]
                        code = master_plan(board, rest)
                        if code and board.board_fen() not in seen:
                            seen.add(board.board_fen())
                            yield number, board.copy(stack=False), move, rest, code, game.headers
                    board.push(move)


def _year(headers) -> int | None:
    year = (headers.get("Date") or "")[:4]
    return int(year) if year.isdigit() else None


def verify(engine: chess.engine.SimpleEngine, args) -> None:
    """Second pass on a longer search: every question of --out is checked again; the ones that fail are dropped.

    The plan rules are applied again first (refilter), so a rule made stricter later does not need a new search."""
    items = json.loads(args.out.read_text(encoding="utf-8"))
    kept = []
    for item in refilter(items):
        board = chess.Board(item["fen"])
        master = chess.Move.from_uci(item["options"][0]["move"])
        result = check(engine, board, master, item["options"][0]["plan"], args)
        if result is None:
            print("dropped", item["id"], item["white"], "-", item["black"], flush=True)
            continue
        kept.append({**item, **result})
    for number, item in enumerate(kept, start=1):
        item["id"] = f"pp{number}"
    args.out.write_text(json.dumps(kept, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"verified {len(kept)} of {len(items)} -> {args.out}")


def main() -> None:
    """Checks the candidates with the engine, keeps a balanced set (at most --per-plan of a category), writes --out."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--per-plan", type=int, default=12, help="at most this many questions of one plan category")
    parser.add_argument("--time", type=float, default=1.0)
    parser.add_argument("--margin", type=int, default=100)
    parser.add_argument("--max-eval", type=int, default=250, help="a calm position: |best evaluation| at most this")
    parser.add_argument("--max-candidates", type=int, default=4000)
    parser.add_argument("--out", type=pathlib.Path, default=OUT)
    parser.add_argument("--stride", type=int, default=1, help="read only every N-th game of the PGN files")
    parser.add_argument("--verify", action="store_true", help="re-check the questions already in --out instead of mining")
    parser.add_argument("--plans", nargs="*", choices=sorted(PLANS), help="mine only these plan categories")
    args = parser.parse_args()
    engine = chess.engine.SimpleEngine.popen_uci(resolve_stockfish_path())
    try:
        if args.verify:
            verify(engine, args)
            return
        found: list[dict] = []
        per_plan: dict[str, int] = {}
        done: set[int] = set()
        checked = 0
        for number, board, master, rest, code, headers in candidates(done, args.stride):
            if len(found) >= args.limit or checked >= args.max_candidates:
                break
            if per_plan.get(code, 0) >= args.per_plan or (args.plans and code not in args.plans):
                continue
            checked += 1
            result = check(engine, board, master, code, args)
            if result is None:
                continue
            done.add(number)
            per_plan[code] = per_plan.get(code, 0) + 1
            item = {"id": f"pp{len(found) + 1}", "fen": board.fen(), "white": surname(headers.get("White", "?")),
                    "black": surname(headers.get("Black", "?")), "year": _year(headers),
                    "continuation": [m.uci() for m in rest], **result}
            found.append(item)
            print(code, item["white"], "-", item["black"], item["year"], result["options"], flush=True)
        args.out.write_text(json.dumps(found, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"checked {checked}, found {len(found)} {per_plan} -> {args.out}")
    finally:
        engine.quit()


if __name__ == "__main__":
    main()
