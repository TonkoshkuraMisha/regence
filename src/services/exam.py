"""
Diagnostic exam (task 22.0). Ten tests by theme catalogue section -- mate (F), double attack (A), line
attacks (B), removing the defender (C), trapping and special positions (D), pawns (E), king attack (G), opening traps (H),
defence (I), endgame (J) -- 10 questions each from easy to hard (puzzle rating 600 -> 2400); separately -- an endgame
exam of 30 positions. A question is a database puzzle position after the opponent's move. The solution is played out to the
end: after a correct
move the opponent replies with a move from the solution, and the player continues -- until mate or the last move of the
combination; each correct
move scores a point. A mistake ends the position (points for moves already found stay); any mate counts as a full
solution. No hints. The result is a strength estimate per section by maximum likelihood using the Elo formula (the share of
solution
moves found is treated as a fractional result of a "game" against the puzzle) and a level by rank. The game rating and puzzle
rating are not
changed.

Big Course level exams (level0 ... level5, task 27.12) follow the same protocol, but the positions come from the fixed
set in src/services/level_exam.py.

Where the data comes from: questions -- the puzzles and puzzle_themes tables (the puzzle's moves field: the first move is the
opponent's, then the solution);
sections and their themes -- the registry src/services/themes.py; results -- the exam_results table (each attempt is a new
row, the totals take the latest per section). The engine is not used. Routes are in src/api/exam.py.
"""

import math
import random
from dataclasses import dataclass

import chess
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DomainValueError
from src.models.puzzle import Puzzle, PuzzleTheme
from src.models.trainer import ExamResult
from src.services import level_exam
from src.services.themes import THEMES

# Theme catalogue sections (src/services/themes.py) that have a diagnostic test.
EXAM_SECTIONS = ("F", "A", "B", "C", "D", "E", "G", "H", "I", "J")
# The separate endgame exam: the same section J themes, but ENDGAME_QUESTIONS positions instead of QUESTIONS.
ENDGAME = "endgame"
QUESTIONS = 10
ENDGAME_QUESTIONS = 30
# Puzzle rating of the first and last question of the test; the rest are evenly spaced between them.
MIN_RATING, MAX_RATING = 600, 2400
# A question is chosen at random from this many puzzles of the section closest by rating -- so that tests do not repeat.
NEAREST = 6
# Levels by rank (a guide to puzzle strength): (upper bound of the estimate, level code) -- the first whose bound is
# above the estimate is taken.
LEVELS: tuple[tuple[int, str], ...] = ((1000, "novice"), (1200, "fourth"), (1400, "third"), (1600, "second"),
                                       (1800, "first"), (2000, "candidate"), (10_000, "master"))


def themes_of(section: str) -> list[str]:
    """Theme codes of a catalogue section; for the endgame exam -- the section J themes."""
    code = "J" if section == ENDGAME else section
    return [theme.code for theme in THEMES if theme.section == code]


def targets(count: int) -> list[int]:
    """Target question ratings: count values evenly from MIN_RATING to MAX_RATING."""
    return [round(MIN_RATING + i * (MAX_RATING - MIN_RATING) / (count - 1)) for i in range(count)]


def question_position(puzzle: Puzzle) -> chess.Board:
    """
    The question position: the puzzle position after the first move from moves (the opponent's move); the solver is to move.
    """
    board = chess.Board(puzzle.fen)
    board.push_uci(puzzle.moves.split()[0])
    return board


async def build(db: AsyncSession, section: str, rng: random.Random | None = None) -> list[dict]:
    """
    Test questions: for each target strength -- one of the puzzles of the section closest by rating, without repeats.
    Questions go
    in ascending rating order; the client gets the puzzle number, position, the solver's colour and the opponent's previous
    move --
    without the solution. A course level exam serves a fixed set (level_exam.questions). An unknown section --
    exam_section_unknown, no puzzles in the section -- exam_section_empty.
    """
    if level_exam.is_level_section(section):
        return level_exam.questions(section)
    if section != ENDGAME and section not in EXAM_SECTIONS:
        raise DomainValueError("exam_section_unknown")
    rng = rng or random.Random()
    codes = themes_of(section)
    chosen: list[Puzzle] = []
    for target in targets(ENDGAME_QUESTIONS if section == ENDGAME else QUESTIONS):
        near = (await db.execute(
            select(Puzzle).join(PuzzleTheme, PuzzleTheme.puzzle_id == Puzzle.id)
            .where(PuzzleTheme.theme.in_(codes), Puzzle.id.not_in([p.id for p in chosen] or [0]))
            .order_by(func.abs(Puzzle.rating - target), Puzzle.id).limit(NEAREST)
        )).scalars().unique().all()
        if near:
            chosen.append(rng.choice(near))
    if not chosen:
        raise DomainValueError("exam_section_empty")
    chosen.sort(key=lambda p: p.rating)
    return [{"id": p.id, "fen": question_position(p).fen(), "color": "white" if question_position(p).turn else "black",
             "previous_move": p.moves.split()[0]} for p in chosen]


@dataclass(frozen=True)
class Progress:
    """
    How far the player got in the solution: correct moves out of how many, whether finished, whether they erred, how the
    opponent will reply.
    """
    correct: int
    total: int
    solved: bool
    failed: bool
    reply: str | None = None

    @property
    def share(self) -> float:
        return self.correct / self.total if self.total else 0.0


def play(start: chess.Board, line: list[str], played: list[str]) -> Progress:
    """
    Checks the player's moves against the solution. line -- the solution from the question position: the player's move, the
    opponent's reply, the player's move...
    A move that gives mate is a full solution even if the database has another. The first wrong move ends the position.
    """
    board = start.copy(stack=False)
    total = (len(line) + 1) // 2
    correct = 0
    for index, uci in enumerate(played[:total]):
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            return Progress(correct, total, False, True)
        if move not in board.legal_moves:
            return Progress(correct, total, False, True)
        board.push(move)
        if uci != line[2 * index]:
            if board.is_checkmate():
                return Progress(total, total, True, False)
            return Progress(correct, total, False, True)
        correct += 1
        if 2 * index + 1 >= len(line):
            return Progress(total, total, True, False)
        board.push_uci(line[2 * index + 1])
    reply = line[2 * correct - 1] if 0 < correct < total else None
    return Progress(correct, total, correct == total, False, reply)


def puzzle_progress(puzzle: Puzzle, played: list[str]) -> Progress:
    """
    Checking the player's moves against a database puzzle solution (moves without the first move -- the opponent made it
    before the question).
    """
    return play(question_position(puzzle), puzzle.moves.split()[1:], played)


def is_correct(puzzle: Puzzle, uci: str) -> bool:
    """The first move of the solution (or any mate) -- for backward compatibility with the "single move" answer."""
    return puzzle_progress(puzzle, [uci]).correct > 0


def estimate(answers: list[tuple[int, float]]) -> int:
    """
    Strength from answers: maximum likelihood of P(correct) = 1 / (1 + 10^((r_puzzle - r)/400)) with a "draw" against 1500.
    The result per puzzle is the share of solution moves found (0...1; True/False are special cases). A "draw" against 1500 --
    an added win and loss against a puzzle rated 1500: they keep the estimate from running to an extreme when all answers
    are correct or all are wrong. Values from 300 to 3000 in steps of 10 are tried.
    """
    def log_likelihood(r: float) -> float:
        total = 0.0
        for rating, score in [*answers, (1500, 1.0), (1500, 0.0)]:
            p = 1 / (1 + 10 ** ((rating - r) / 400))
            total += float(score) * math.log(p) + (1 - float(score)) * math.log(1 - p)
        return total

    return max(range(300, 3001, 10), key=log_likelihood)


def level(rating: int) -> str:
    """Level code by strength estimate (the LEVELS table): below 1000 -- novice, ..., from 2000 -- master."""
    return next(code for limit, code in LEVELS if rating < limit)


@dataclass
class Graded:
    """
    Exam result: how many positions solved, the strength estimate, a per-position breakdown, a profile by branch and points
    for correct moves.
    """
    section: str
    correct: int
    total: int
    estimate: int
    review: list[dict]
    branches: dict[str, dict] | None = None
    # Points: correct moves across all positions out of the possible (task B.4 -- the solution is played out to the end).
    points: int = 0
    max_points: int = 0


def _review_row(qid: int, played: list[str], progress: Progress, board: chess.Board, solution: str, rating: int) -> dict:
    return {"id": qid, "answer": played[0] if played else "0000", "correct": progress.solved, "solution": solution,
            "solution_san": board.san(chess.Move.from_uci(solution)), "rating": rating,
            "points": progress.correct, "max_points": progress.total}


def _graded(section: str, review: list[dict], scored: list[tuple[int, float]],
            branches: dict[str, dict] | None = None) -> Graded:
    return Graded(section, sum(int(row["correct"]) for row in review), len(review), estimate(scored), review, branches,
                  points=sum(row["points"] for row in review), max_points=sum(row["max_points"] for row in review))


def _grade_level(user_id: int, section: str, answers: list[tuple[int, list[str]]]) -> tuple[Graded, ExamResult]:
    """Check of a course level exam against the fixed set: the result with a profile by branch and a result row."""
    review: list[dict] = []
    scored: list[tuple[int, float]] = []
    for qid, played in answers:
        item = level_exam.question(section, qid)
        if item is None:
            raise DomainValueError("exam_question_unknown")
        progress = level_exam.progress(item, played)
        scored.append((item["rating"], progress.share))
        review.append({**_review_row(qid, played, progress, chess.Board(item["fen"]), item["answer"], item["rating"]),
                       "branch": item["branch"]})
    result = _graded(section, review, scored, level_exam.branch_profile(review))
    return result, ExamResult(user_id=user_id, section=section, correct=result.correct, total=result.total,
                              estimate=result.estimate)


async def _section_puzzle(db: AsyncSession, section: str, puzzle_id: int) -> Puzzle:
    """
    The question's puzzle if it belongs to the section's themes; otherwise exam_question_unknown -- an arbitrary database
    puzzle
    cannot be checked this way by the exam's move.
    """
    if section != ENDGAME and section not in EXAM_SECTIONS:
        raise DomainValueError("exam_section_unknown")
    puzzle = await db.get(Puzzle, puzzle_id)
    themes = set((await db.scalars(select(PuzzleTheme.theme).where(PuzzleTheme.puzzle_id == puzzle_id))).all())
    if puzzle is None or not themes & set(themes_of(section)):
        raise DomainValueError("exam_question_unknown")
    return puzzle


async def check_moves(db: AsyncSession, section: str, question_id: int, played: list[str]) -> Progress:
    """
    The player's move during the test: whether correct and how the opponent replies (the whole solution is not given to the
    client).
    """
    if level_exam.is_level_section(section):
        item = level_exam.question(section, question_id)
        if item is None:
            raise DomainValueError("exam_question_unknown")
        return level_exam.progress(item, played)
    return puzzle_progress(await _section_puzzle(db, section, question_id), played)


async def grade(db: AsyncSession, user_id: int, section: str, answers: list[tuple[int, list[str]]]) -> Graded:
    """
    Checking exam answers for a section: the solution of each position is played out to the end, points for correct moves and
    the
    strength estimate are counted. Returns the result (Graded). answers -- pairs (question number, player's moves). The
    result is added to
    exam_results without commit -- the route does that. A question not from this section -- exam_question_unknown.
    """
    if level_exam.is_level_section(section):
        graded, row = _grade_level(user_id, section, answers)
        db.add(row)
        return graded
    if section != ENDGAME and section not in EXAM_SECTIONS:
        raise DomainValueError("exam_section_unknown")
    codes = set(themes_of(section))
    ids = [pid for pid, _ in answers]
    puzzles = {p.id: p for p in (await db.execute(select(Puzzle).where(Puzzle.id.in_(ids)))).scalars().all()}
    themes: dict[int, set[str]] = {}
    for pid, theme in (await db.execute(select(PuzzleTheme.puzzle_id, PuzzleTheme.theme)
                                        .where(PuzzleTheme.puzzle_id.in_(ids)))).tuples():
        themes.setdefault(pid, set()).add(theme)
    review: list[dict] = []
    scored: list[tuple[int, float]] = []
    for pid, played in answers:
        puzzle = puzzles.get(pid)
        if puzzle is None or not themes.get(pid, set()) & codes:
            raise DomainValueError("exam_question_unknown")
        progress = puzzle_progress(puzzle, played)
        scored.append((puzzle.rating, progress.share))
        review.append(_review_row(pid, played, progress, question_position(puzzle), puzzle.moves.split()[1],
                                  puzzle.rating))
    result = _graded(section, review, scored)
    db.add(ExamResult(user_id=user_id, section=section, correct=result.correct, total=result.total,
                      estimate=result.estimate))
    return result


async def latest(db: AsyncSession, user_id: int) -> dict:
    """
    The latest result per test and the overall level -- the mean of the estimates of completed sections (without the endgame
    one).
    """
    rows = (await db.execute(
        select(ExamResult).where(ExamResult.user_id == user_id).order_by(ExamResult.created_at, ExamResult.id)
    )).scalars().all()
    last = {row.section: row for row in rows}
    sections = {key: {"correct": r.correct, "total": r.total, "estimate": r.estimate, "level": level(r.estimate),
                      "at": r.created_at.isoformat() if r.created_at else None} for key, r in last.items()}
    diagnostic = [r.estimate for key, r in last.items() if key in EXAM_SECTIONS]
    overall = round(sum(diagnostic) / len(diagnostic)) if diagnostic else None
    return {"sections": sections, "overall": overall, "level": level(overall) if overall else None,
            "passed": len(diagnostic), "of": len(EXAM_SECTIONS)}
