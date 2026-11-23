# --- FILE: src/services/guess_quiz.py ---
"""
Questions after a game in the "Guess the move" mode (task 14.3, "whole game"): three questions about the master game just
analysed -- who won, where the key moment was and whether the game ended in mate. The answers are known from the game data
(`games.result`, PGN) and the selected moments (`guess_positions.gap_cp` -- the gap of the best move): the engine is not
called.
The rules are pure functions without a database: the options and correct answers are deterministic (the seed is the game id),
so the server
stores nothing: checking recomputes the same questions. The server gives option codes, the client assembles the text.
"""

import io
import random

import chess
import chess.pgn

# Questions: question code -> default options (for the "key moment" the options are built from the game).
WINNER_OPTIONS = ("white", "black", "draw")
MATE_OPTIONS = ("yes", "no")
# How many options the key moment question has: the correct one and up to two plausible ones.
KEY_MOMENT_OPTIONS = 3
# The minimum of selected moments to ask about the key one (with a single moment the question gives away the answer).
MIN_MOMENTS_FOR_KEY = 2


def moment_code(ply: int) -> str:
    """A move code for an option: the move number and side ("12w" -- White's 12th move; ply -- the ply counted from zero)."""
    return f"{ply // 2 + 1}{'w' if ply % 2 == 0 else 'b'}"


def winner_of(result: str | None) -> str:
    """The winner by the game result: white / black / draw (everything except 1-0 and 0-1 is a draw)."""
    return {"1-0": "white", "0-1": "black"}.get(result or "", "draw")


def plies_and_mate(pgn: str | None) -> tuple[int, bool]:
    """
    (the number of plies, whether the game ends in mate on the board) from the move record; an unreadable record -- (0,
    False).
    """
    if not pgn:
        return 0, False
    try:
        game = chess.pgn.read_game(io.StringIO(pgn))
    except (ValueError, KeyError):
        return 0, False
    if game is None:
        return 0, False
    end = game.end()
    return end.ply(), end.board().is_checkmate()


def build_quiz(
        game_id: int, result: str | None, final_mate: bool, moments: list[tuple[int, int]], total_plies: int,
) -> tuple[list[dict], dict[str, str]]:
    """
    (questions, correct answers). moments -- (ply, the best move's gap) of the game's selected moments; the key moment is the
    one with
    the biggest gap. The wrong options of the key moment are other moves of the game (the seed is the game id, the order
    is constant). The key moment question exists only if there are at least MIN_MOMENTS_FOR_KEY moments.
    """
    questions = [{"id": "winner", "options": list(WINNER_OPTIONS)}]
    answers = {"winner": winner_of(result)}
    if len(moments) >= MIN_MOMENTS_FOR_KEY:
        key_ply = max(moments, key=lambda m: (m[1], -m[0]))[0]
        rng = random.Random(game_id)
        # The game goes for the side that is to move in the moment's position; the wrong options are moves of the same side,
        # not selected.
        selected = {ply for ply, _gap in moments}
        pool = [p for p in range(key_ply % 2, max(total_plies, key_ply + 1), 2) if p not in selected]
        wrong = rng.sample(pool, min(KEY_MOMENT_OPTIONS - 1, len(pool)))
        options = [moment_code(p) for p in [key_ply, *wrong]]
        rng.shuffle(options)
        questions.append({"id": "key_moment", "options": options})
        answers["key_moment"] = moment_code(key_ply)
    questions.append({"id": "mate", "options": list(MATE_OPTIONS)})
    answers["mate"] = "yes" if final_mate else "no"
    return questions, answers


def check_quiz(answers: dict[str, str], correct: dict[str, str]) -> dict:
    """
    The result: {score, total, results: {question: whether correct}, correct: the correct answers}. No answer to a question
    -- wrong.
    """
    results = {question: answers.get(question) == right for question, right in correct.items()}
    return {"score": sum(results.values()), "total": len(correct), "results": results, "correct": correct}
