# --- FILE: src/services/guess.py ---
"""
"Guess the master's move" (task 14.3): serving selected positions and scoring the answer.

Points: the master's move -- 100; another move no worse than the best by NEAR_CP -- 80; worse -- by loss: 80 - (loss -
NEAR_CP) / 5,
no less than zero. Scoring uses the saved engine lines (up to three best moves), without running the engine: a move outside
these lines is
no better than the second line (selection guarantees its lag), so its loss is the gap of the best move plus a margin.

The "choice from candidates" mode (for beginners): the player picks a move from CANDIDATES options -- the master's move and
other moves
from the saved engine lines. By the selection rule each of them is noticeably worse than the master's move (the gap gap_cp),
so the
task stays solvable by calculation; the order of options is shuffled but is always the same for one position.

A position's difficulty is its rating: a signed-in player's answer changes it, like a puzzle game against a solver (Elo
against the
player's puzzle rating): found the master's move -- the position "lost", not -- "won". The player's rating does not change.

Where the data comes from: positions -- the guess_positions table (the master's move, the engine lines, the gap gap_cp,
themes, series,
the plays and solved counters); it is filled offline by scripts/build_guess_positions.py from the archive games (the games
table) by the
rules of src/services/guess_selection.py. The server does not run the engine for this section. The explanation of the
master's move is
src/services/coach.py. The legality of the player's move is checked by the route (src/api/guess.py).
"""

import io
import random

import chess
import chess.pgn
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.game import Game
from src.models.guess import GuessPosition
from src.models.user import User
from src.services.coach import advice_for_position, hint_for_position
from src.services.guess_quiz import build_quiz, plies_and_mate
from src.services.guess_selection import book_plies, in_opening, is_technical_endgame, position_themes

# Points for the master's move and for another move that is worse than the best by no more than NEAR_CP centipawns.
MASTER_SCORE = 100
NEAR_SCORE = 80
NEAR_CP = 30
# A margin on the loss of a move that is not in the saved engine lines: loss = the best move's gap + this margin.
UNKNOWN_EXTRA_CP = 50
# Attempts with hints: MAX_ATTEMPTS attempts are given per position (a wrong move before the last one -- "try again", without
# a result); for each hint used and each attempt beyond the first a separate penalty is subtracted from the points.
MAX_ATTEMPTS = 3
HINT_PENALTY = 10
ATTEMPT_PENALTY = 10
# How many last plies of the game are shown before the position.
CONTEXT_MOVES = 8
# How many options the "choice from candidates" mode shows: the master's move and up to two moves from the engine lines.
CANDIDATES = 3
# A position is picked within +-DIFFICULTY_BAND of the requested difficulty.
DIFFICULTY_BAND = 300
# The position rating: for the first PROVISIONAL_PLAYS answers it changes with the coefficient K_PROVISIONAL, then K_STABLE;
# it does not leave the bounds MIN_DIFFICULTY...MAX_DIFFICULTY.
PROVISIONAL_PLAYS = 20
K_PROVISIONAL, K_STABLE = 32, 12
MIN_DIFFICULTY, MAX_DIFFICULTY = 600, 3000


def score_answer(position: GuessPosition, move_uci: str) -> tuple[int, int]:
    """
    (points, loss in cp) for a player's answer. The loss of a move from the saved engine lines is the difference from the
    best evaluation; of a move
    outside the lines -- gap_cp + UNKNOWN_EXTRA_CP. Points for a loss above NEAR_CP: minus a point for every 5 centipawns.
    """
    if move_uci == position.move_uci:
        return MASTER_SCORE, 0
    known = {uci: cp for uci, cp in position.lines}
    loss = position.best_cp - known[move_uci] if move_uci in known else position.gap_cp + UNKNOWN_EXTRA_CP
    loss = max(0, loss)
    if loss <= NEAR_CP:
        return NEAR_SCORE, loss
    return max(0, NEAR_SCORE - (loss - NEAR_CP) // 5), loss


def hint(position: GuessPosition, step: int) -> dict:
    """A hint for the position by the mentor's levels (a nudge, a piece, full advice with an arrow of the master's move)."""
    return hint_for_position(chess.Board(position.fen), position.move_uci, step)


def _game_context(game: Game, ply: int) -> dict:
    """The players, the event and the game's moves before the position (for the caption and the move strip)."""
    parsed = chess.pgn.read_game(io.StringIO(game.pgn or ""))
    if parsed is None:
        return {"white": "?", "black": "?", "event": None, "date": None, "previous": [], "last_move": None}
    board = parsed.board()
    sans: list[str] = []
    last_move = None
    for index, move in enumerate(parsed.mainline_moves()):
        if index >= ply:
            break
        sans.append(board.san(move))
        board.push(move)
        last_move = move.uci()
    headers = parsed.headers
    return {
        "white": headers.get("White", "?"), "black": headers.get("Black", "?"),
        "event": headers.get("Event") if headers.get("Event", "?") != "?" else None,
        "date": (headers.get("Date") or "")[:4] or None,
        "previous": sans[-CONTEXT_MOVES:], "first_previous_ply": max(0, len(sans) - CONTEXT_MOVES),
        "last_move": last_move,
    }


def candidate_moves(position: GuessPosition) -> list[dict]:
    """
    Options of the "choice from candidates" mode: the master's move and moves from the engine lines (without repeats), no
    more than CANDIDATES,
    in a shuffled order that is always the same for a position (the seed is its id). A move is UCI plus the SAN notation.
    """
    moves = [position.move_uci] + [uci for uci, _cp in position.lines if uci != position.move_uci]
    chosen = list(dict.fromkeys(moves))[:CANDIDATES]
    random.Random(position.id).shuffle(chosen)
    board = chess.Board(position.fen)
    return [{"uci": uci, "san": board.san(chess.Move.from_uci(uci))} for uci in chosen]


async def payload(db: AsyncSession, position: GuessPosition, with_candidates: bool = False) -> dict:
    """
    A "Guess the master's move" position for the client: board, whose move, difficulty, place in the series and game details.
    The master's
    move is not given; with_candidates -- add options to choose from (candidate_moves), only at the client's request.
    """
    game = await db.get(Game, position.game_id)
    series_length = 0
    if position.series_id is not None:
        series_length = (await db.execute(
            select(func.count()).select_from(GuessPosition).where(GuessPosition.series_id == position.series_id)
        )).scalar_one()
    return {
        "id": position.id, "game_id": position.game_id, "ply": position.ply, "fen": position.fen,
        "side": "white" if position.ply % 2 == 0 else "black", "move_number": position.ply // 2 + 1,
        "difficulty": position.difficulty,
        "series_id": position.series_id, "series_index": position.series_index, "series_length": series_length,
        **(_game_context(game, position.ply) if game else {}),
        **({"candidates": candidate_moves(position)} if with_candidates else {}),
    }


async def pick_position(db: AsyncSession, target: int, series: bool) -> GuessPosition | None:
    """A random position (or a series start) near the difficulty target; if none is near -- any."""
    query = select(GuessPosition)
    if series:
        query = query.where(GuessPosition.series_id.is_not(None), GuessPosition.series_index == 0)
    near = query.where(GuessPosition.difficulty.between(target - DIFFICULTY_BAND, target + DIFFICULTY_BAND))
    for candidate_query in (near, query):
        ids = (await db.execute(candidate_query.with_only_columns(GuessPosition.id))).scalars().all()
        if ids:
            return await db.get(GuessPosition, random.choice(ids))
    return None


async def series_next(db: AsyncSession, position: GuessPosition) -> GuessPosition | None:
    """The next position of the same series (a series is several master moves in a row in one game) or None."""
    if position.series_id is None:
        return None
    return (await db.execute(select(GuessPosition).where(
        GuessPosition.series_id == position.series_id, GuessPosition.series_index == position.series_index + 1,
    ))).scalar_one_or_none()


async def game_positions(db: AsyncSession, game_id: int) -> list[GuessPosition]:
    """All selected positions of a game in move order."""
    return list((await db.execute(
        select(GuessPosition).where(GuessPosition.game_id == game_id).order_by(GuessPosition.ply)
    )).scalars())


async def game_quiz(db: AsyncSession, game_id: int) -> tuple[list[dict], dict[str, str]] | None:
    """Questions after the game and the correct answers (guess_quiz.build_quiz) or None if the game has no selected moments."""
    positions = await game_positions(db, game_id)
    game = await db.get(Game, game_id)
    if game is None or not positions:
        return None
    total_plies, mate = plies_and_mate(game.pgn)
    return build_quiz(game_id, game.result, mate, [(p.ply, p.gap_cp) for p in positions], total_plies)


def rating_after(position_rating: int, solver_rating: int, plays: int, solved: bool) -> int:
    """
    The new position rating after a player's answer with the rating solver_rating (Elo, the position is the "opponent").
    plays -- how many
    times the position has already been solved (the coefficient depends on it), solved -- whether the master's move was found.
    """
    k = K_PROVISIONAL if plays < PROVISIONAL_PLAYS else K_STABLE
    expected = 1 / (1 + 10 ** ((solver_rating - position_rating) / 400))  # the expected "win" of the position
    value = position_rating + round(k * ((0 if solved else 1) - expected))
    return max(MIN_DIFFICULTY, min(MAX_DIFFICULTY, value))


async def first_positions(db: AsyncSession, game_ids: list[int]) -> dict[int, int]:
    """A game -> the first selected position (by ply): the "Guess the move" buttons in the master games list."""
    if not game_ids:
        return {}
    rows = await db.execute(
        select(GuessPosition.game_id, GuessPosition.id).where(GuessPosition.game_id.in_(game_ids))
        .order_by(GuessPosition.game_id, GuessPosition.ply)
    )
    result: dict[int, int] = {}
    for game_id, position_id in rows:
        result.setdefault(game_id, position_id)
    return result


async def answer(
        db: AsyncSession, position: GuessPosition, move_uci: str, user: User | None = None,
        attempt: int | None = None, hints: int = 0,
) -> dict:
    """
    Points, the master's move, engine lines, themes and the mentor's explanation of the master's move. It also updates the
    position's
    counters (plays, solved) and, if a signed-in player answers, its rating -- by their puzzle rating (with commit). A guest's
    answer does not change the position rating.

    attempt -- the attempt number (1...MAX_ATTEMPTS) in the "three attempts" mode; without it the answer is always final. A
    move worse than
    "almost equivalent" is not analysed until the last attempt: the answer is {retry, attempts_left, loss_cp}, the counters
    do not
    change. The final points are reduced by the penalties for hints (hints) and extra attempts; the position counts as solved
    (for its rating) only if the master's move is found on the first attempt and without hints.
    """
    board = chess.Board(position.fen)
    score, loss = score_answer(position, move_uci)
    if attempt is not None and score < NEAR_SCORE and attempt < MAX_ATTEMPTS:
        return {"retry": True, "attempts_left": MAX_ATTEMPTS - attempt, "loss_cp": loss}
    clean = score == MASTER_SCORE and (attempt or 1) == 1 and hints == 0
    score = max(0, score - HINT_PENALTY * hints - ATTEMPT_PENALTY * ((attempt or 1) - 1))
    if user is not None:
        position.difficulty = rating_after(position.difficulty, user.puzzle_rating, position.plays, clean)
    position.plays += 1
    if clean:
        position.solved += 1
    await db.commit()
    master = chess.Move.from_uci(position.move_uci)
    advice = advice_for_position(board, position.move_uci)
    next_in_series = await series_next(db, position)
    return {
        "score": score, "loss_cp": loss, "master_move": position.move_uci, "master_san": board.san(master),
        "lines": [{"uci": uci, "san": board.san(chess.Move.from_uci(uci)), "cp": cp} for uci, cp in position.lines],
        "comment": advice["comment"], "arrows": advice["arrows"], "themes": position.themes or [],
        "next_id": next_in_series.id if next_in_series else None,
    }


def _boards(pgn: str) -> tuple[list[chess.Board], int]:
    """Game positions with a move stack (the index is the ply) and the length of the book opening."""
    parsed = chess.pgn.read_game(io.StringIO(pgn))
    if parsed is None:
        return [], 0
    moves = list(parsed.mainline_moves())
    board = parsed.board()
    boards = [board.copy()]
    for move in moves:
        board.push(move)
        boards.append(board.copy())
    return boards, book_plies(moves)


def _renumber_series(positions: list[GuessPosition]) -> None:
    """After removing some positions: series shorter than two moves are dissolved, numbers inside a series are consecutive."""
    groups: dict[int, list[GuessPosition]] = {}
    for position in positions:
        if position.series_id is not None:
            groups.setdefault(position.series_id, []).append(position)
    for members in groups.values():
        members.sort(key=lambda p: p.ply)
        for index, position in enumerate(members):
            position.series_id = position.series_id if len(members) > 1 else None
            position.series_index = index if len(members) > 1 else 0


async def refilter(db: AsyncSession) -> tuple[int, int]:
    """
    Positions selected by the old rules -> current ones: remove the book opening (table 16.1) and the technical endgame,
    assign themes where there are none (by the master's move, without an engine). Returns (removed, got themes).
    """
    removed = tagged = 0
    game_ids = (await db.execute(select(GuessPosition.game_id).distinct())).scalars().all()
    for game_id in game_ids:
        game = await db.get(Game, game_id)
        positions = await game_positions(db, game_id)
        boards, book = _boards(game.pgn or "") if game else ([], 0)
        kept = []
        for position in positions:
            board = boards[position.ply] if position.ply < len(boards) else None
            if board is None or in_opening(board, book) or is_technical_endgame(board):
                await db.delete(position)
                removed += 1
                continue
            if not position.themes:
                position.themes = position_themes(board, chess.Move.from_uci(position.move_uci), [])
                tagged += bool(position.themes)
            kept.append(position)
        _renumber_series(kept)
        await db.commit()
    return removed, tagged
