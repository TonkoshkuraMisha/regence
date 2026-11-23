"""
Check of school lessons against the engine (task 14.1). Not for CI: needs Stockfish and time.

The legality of moves and the presence of correct answers are checked by the client test (validateLesson in CI). This script
chess correctness: in every "find the move" question
* every correct answer is no worse than the engine's best move by more than --tolerance cp (a mate - only if the engine also
  sees a mate no longer);
* the best answer has no rival nearby: the second-best move that is not among the answers is inferior to it by at least
  --margin cp - otherwise the question is "guessed", not solved, and that move must be added to the answers;
* every move with a separate "wrong" response is really worse than the best by at least --margin cp.

    python scripts/verify_lessons.py
    python scripts/verify_lessons.py --time 1.0 --only tactics-double-attack
"""

import argparse
import json
import sys
from pathlib import Path

import chess
import chess.engine

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
LESSONS_DIR = ROOT / "frontend" / "src" / "content" / "lessons"
MATE = 100_000


def score(info: dict, turn: chess.Color) -> int:
    """Extracts the position evaluation in centipawns from the point of view of the player to move."""
    return info["score"].pov(turn).score(mate_score=MATE)


def evaluate(engine: chess.engine.SimpleEngine, board: chess.Board, move: chess.Move, limit) -> int:
    """Evaluates a specific move in a position via the Stockfish engine's root_moves."""
    info = engine.analyse(board, limit, root_moves=[move])
    return score(info, board.turn)


DECISIVE = 1500  # cp: beyond this it is a win, comparing "by how much" is meaningless


def check_position(engine, board: chess.Board, task: dict, limit, tolerance: int, margin: int) -> list[str]:
    """Uses the engine to check that the answer is unique and the false moves in a lesson step."""
    problems = []
    infos = engine.analyse(board, limit, multipv=min(5, board.legal_moves.count()))
    lines = [(info["pv"][0], score(info, board.turn)) for info in infos if info.get("pv")]
    best_move, best = lines[0]
    answers = [chess.Move.from_uci(u) for u in task["answers"]]

    answer_scores = {}
    multipv = dict(lines)
    for move in answers:
        # A MultiPV move - its evaluation is from the same line (a separate search after the move is shallower, loses a mate).
        value = multipv[move] if move in multipv else evaluate(engine, board, move, limit)
        answer_scores[move] = value
        # Both evaluations are decisive (a win with either move) - same result, the lesson move is no worse in essence.
        if value < best - tolerance and not (value >= DECISIVE and best >= DECISIVE):
            problems.append(f"answer {move.uci()} is worse than the best {best_move.uci()} ({value} vs {best} cp)")

    top_answer = max(answer_scores.values())
    rivals = [(m, v) for m, v in lines if m not in answers]
    if rivals and rivals[0][1] > top_answer - margin and top_answer < MATE // 2:
        m, v = rivals[0]
        problems.append(f"move {m.uci()} is almost no worse than the answer ({v} vs {top_answer} cp) - question is guessable")

    for uci in task.get("wrong", {}):
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            # The engine would evaluate even an impossible move (searchmoves does not check it) - say so plainly.
            problems.append(f"\"wrong\" move {uci} is impossible in this position - nobody will see the response")
            continue
        value = evaluate(engine, board, move, limit)
        if value > best - margin:
            problems.append(f"\"wrong\" move {uci} is actually not bad ({value} vs {best} cp)")
    return problems


def check_lesson(path: Path, engine, limit, tolerance: int, margin: int) -> list[str]:
    """Checks all interactive steps and the exam of one lesson file."""
    lesson = json.loads(path.read_text(encoding="utf-8"))
    problems = []
    questions = [("step", i, s) for i, s in enumerate(lesson["steps"], 1)]
    questions += [("exam", i, s) for i, s in enumerate(lesson["exam"], 1)]
    for kind, number, step in questions:
        if step["type"] != "find_move":
            continue
        board = chess.Board(step["fen"])
        for move_number, task in enumerate(step["line"], 1):
            where = f"{lesson['id']}, {kind} {number}, move {move_number}"
            problems += [f"{where}: {p}" for p in check_position(engine, board, task, limit, tolerance, margin)]
            board.push_uci(task["answers"][0])
            if task.get("reply"):
                board.push_uci(task["reply"])
    return problems


def main() -> None:
    """Runs the check of school lessons against the Stockfish engine."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--time", type=float, default=0.5, help="Seconds per position")
    parser.add_argument("--tolerance", type=int, default=30, help="By how much a correct answer may be inferior to the best")
    parser.add_argument("--margin", type=int, default=100, help="Lead of the answer over other moves")
    parser.add_argument("--only", nargs="*", help="lesson ids")
    args = parser.parse_args()

    from src.services.bots.base import resolve_stockfish_path

    path = resolve_stockfish_path()
    if not path:
        raise SystemExit("Stockfish not found: python scripts/setup_stockfish.py")
    files = sorted(p for p in LESSONS_DIR.glob("*.json") if p.name != "courses.json")
    if args.only:
        files = [p for p in files if p.stem in args.only]

    problems = []
    with chess.engine.SimpleEngine.popen_uci(path) as engine:
        for file in files:
            found = check_lesson(file, engine, chess.engine.Limit(time=args.time), args.tolerance, args.margin)
            print(f"{file.stem}: {'OK' if not found else f'{len(found)} findings'}", flush=True)
            problems += found
    for problem in problems:
        print(f"  - {problem}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
