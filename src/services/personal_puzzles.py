# --- FILE: src/services/personal_puzzles.py ---
"""
Puzzles from the player's games (task 13.5). After the review of a finished game, moments are searched where the player
(not a bot) erred or missed a win, and personal "Your mistakes" puzzles are made from them - by the same criteria of
objective solvability as "Guess the Master's Move" (14.3):

* the game move is a mistake or a blunder by the review (loss >= MIN_LOSS cp);
* the best move has a margin: the second-best move is worse by >= MIN_GAP cp (or the best mates and the second does not) -
otherwise
  the puzzle is guessed rather than solved;
* the best move is not an obvious capture of an undefended piece;
* no more than MAX_PER_PLAYER puzzles per player per game (the costliest mistakes);
* a Fischer random game (an imported Chess960 game, 24.1) gives a puzzle only from a position that the ordinary rules read
  the same way (``readable_as_standard``): the puzzle board and ``chess.Board(fen)`` do not know 960 castling.

Spaced repetition: a new puzzle is available at once; a wrong answer returns it after 1 day, the first correct one after
3 days, the second correct in a row makes it mastered (done). INTERVALS_DAYS also holds intervals of 7 and 21 days, but
with SOLVES_TO_MASTER = 2 a puzzle never reaches them: after the second correct answer it is already mastered.

Data: the game review is games.analysis_json (written by analysis_service.py) and imported_games.analysis_json (written by
game_import.py), puzzles are the personal_puzzles table. Extraction is run by the background task after the review
(src/worker/tasks.py) and by game import (src/api/game_import.py). The engine is used only to check the margin of the best move
(two best moves, depth ENGINE_DEPTH), via the pool; without the engine no puzzles are created from a game.
"""

import asyncio
import datetime as dt
import json
import logging
from collections.abc import Iterable

import chess
import chess.engine
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DomainValueError
from src.models.game import Game
from src.models.imported_game import ImportedGame
from src.models.puzzle import PersonalPuzzle
from src.models.user import User
from src.services.bots.base import resolve_stockfish_path
from src.services.engine_pool import EngineUnavailableError, engine_work, get_engine_pool
from src.services.game_engine import read_pgn_game
from src.services.mentor_service import analyze_move
from src.services.themes import themes_for_motif

logger = logging.getLogger(__name__)

MIN_LOSS = 100  # the smallest loss of a game move (cp) at which a mistake qualifies as a puzzle
MIN_GAP = 200  # by how many cp the best move must lead the second so that the solution is unique
MAX_PER_PLAYER = 3  # puzzles per player from one game
ENGINE_DEPTH = 14  # depth of checking the two best moves
MATE_CP = 10_000  # conventional mate evaluation in centipawns; an evaluation from MATE_CP - 100 counts as mate
# After how many days a puzzle comes back, by the index personal_puzzles.interval_index (see the module docstring: with
# SOLVES_TO_MASTER = 2 only the first two values are used).
INTERVALS_DAYS = (1, 3, 7, 21)
SOLVES_TO_MASTER = 2  # correct answers in a row after which the puzzle is mastered and no longer shown
# Separator of theme codes in the personal_puzzles.themes column (see join_themes / split_themes).
THEMES_SEPARATOR = ","


def _score(info: chess.engine.InfoDict, turn: chess.Color) -> int:
    """Engine line evaluation in centipawns from the point of view of the side turn; mate - about +-MATE_CP."""
    return int(info["score"].pov(turn).score(mate_score=MATE_CP) or 0)


def top_two(board: chess.Board) -> list[tuple[str, int]] | None:
    """
    Two best moves with an evaluation from the point of view of the side to move (Stockfish via the pool, depth
    ENGINE_DEPTH, two lines). None - no engine. One element - the position has the only legal move. Synchronous: call in a
    thread.
    """
    path = resolve_stockfish_path()
    if not path:
        return None
    with get_engine_pool(path).acquire() as engine:
        infos = engine.analyse(board, chess.engine.Limit(depth=ENGINE_DEPTH), multipv=2)
    if not isinstance(infos, list):
        infos = [infos]
    return [(info["pv"][0].uci(), _score(info, board.turn)) for info in infos if info.get("pv")]


def obvious_capture(board: chess.Board, move: chess.Move) -> bool:
    """
    Capturing an undefended piece is visible without calculation, no puzzle comes out of it. "Undefended" - on the capture
    square no piece of its side attacks; an en passant capture is not considered obvious.
    """
    target = board.piece_at(move.to_square)
    if target is None or board.is_en_passant(move):
        return False
    return not board.attackers(target.color, move.to_square)


def is_solvable(board: chess.Board, best: chess.Move, candidates: list[tuple[str, int]]) -> bool:
    """
    Whether a puzzle is objectively solvable: the best move is not an obvious capture, it is not the only legal move and it
    leads the second-best move by MIN_GAP (or mates and the second does not). candidates - the ``top_two`` answer; the best
    move of the game review must match the first move of this deeper check, otherwise the puzzle is not created.
    """
    if obvious_capture(board, best):
        return False
    if not candidates or candidates[0][0] != best.uci():
        return False
    if len(candidates) == 1:
        return False  # the only legal move - nothing to solve
    (_, first), (_, second) = candidates[0], candidates[1]
    if first >= MATE_CP - 100 and second < MATE_CP - 100:
        return True
    return first - second >= MIN_GAP


def readable_as_standard(board: chess.Board, after_castling: bool) -> bool:
    """
    Whether a position can be a puzzle under the ordinary rules. Any position of ordinary chess can; a Fischer random
    position only when no castling right is left (a 960 right would be read as a right of the standard setup) and the
    previous move, shown on the puzzle board, was not a castling (written "king takes its rook" in 960).
    """
    return not board.chess960 or (not board.castling_rights and not after_castling)


def join_themes(codes: Iterable[str]) -> str:
    """Themes of a personal puzzle as stored (personal_puzzles.themes): registry codes separated by commas."""
    return THEMES_SEPARATOR.join(codes)


def split_themes(stored: str | None) -> list[str]:
    """Theme codes from personal_puzzles.themes - the inverse of join_themes; an empty value means no themes."""
    return [code for code in (stored or "").split(THEMES_SEPARATOR) if code]


def themes_of(board: chess.Board, move: chess.Move) -> list[str]:
    """Registry theme codes that the move creates on the board - from the mentor detector's motifs."""
    facts = analyze_move(board, move)
    after = board.copy(stack=False)
    after.push(move)
    codes: list[str] = []
    for motif in facts.created:
        piece = after.piece_at(motif.square)
        for code in themes_for_motif(motif.code, piece.symbol().lower() if piece else None):
            if code not in codes:
                codes.append(code)
    return codes


async def extract_for_game(db: AsyncSession, game_id: int) -> int:
    """
    Personal puzzles from a reviewed game - for each side the human played, not a bot. Without a review
    (games.analysis_json) or without PGN there are no puzzles. A repeated call duplicates nothing. Returns the number of
    new puzzles.
    """
    game = await db.get(Game, game_id)
    if game is None or not game.analysis_json or not game.pgn:
        return 0
    players: dict[str, User] = {}
    for color, user_id in (("white", game.white_player_id), ("black", game.black_player_id)):
        user = await db.get(User, user_id)
        if user is not None and not user.is_bot:
            players[color] = user
    existing = set((await db.execute(
        select(PersonalPuzzle.user_id, PersonalPuzzle.ply).where(PersonalPuzzle.game_id == game_id)
    )).all())
    return await _extract(db, game.pgn, game.analysis_json, players, existing, {"game_id": game_id}, f"game {game_id}")


async def extract_for_imported(db: AsyncSession, imported_id: int) -> int:
    """The same for a game from another site (task 24.1): puzzles only for the player's side - the opponent is not ours."""
    game = await db.get(ImportedGame, imported_id)
    if game is None or not game.analysis_json:
        return 0
    user = await db.get(User, game.user_id)
    if user is None:
        return 0
    existing = set((await db.execute(
        select(PersonalPuzzle.user_id, PersonalPuzzle.ply).where(PersonalPuzzle.imported_game_id == imported_id)
    )).all())
    return await _extract(db, game.pgn, game.analysis_json, {game.color: user}, existing,
                          {"imported_game_id": imported_id}, f"imported game {imported_id}")


async def _extract(db: AsyncSession, pgn: str, analysis_json: str, players: dict[str, User],
                   existing: set, source: dict[str, int], label: str) -> int:
    """
    General part of the extraction. players - colour ("white" / "black") -> the player for whom puzzles are searched;
    existing - already created (player, ply) pairs; source - the source column of the puzzle (game_id or imported_game_id).

    Order: from the review the player's moves classified Mistake or Blunder with a loss from MIN_LOSS are taken, for which
    the best move is known and differs from the played one; in descending order of loss each is checked by the engine
    (``is_solvable``), until MAX_PER_PLAYER is reached (puzzles already created for the game count toward it). If the
    engine is unavailable, extraction stops with an early return - without commit: the puzzles added by then are saved
    only if the calling code commits the session.
    """
    if not players:
        return 0
    try:
        moves_report = json.loads(analysis_json).get("moves", [])
    except ValueError:
        return 0
    pgn_game = read_pgn_game(pgn)
    if pgn_game is None:
        return 0
    board = pgn_game.board()
    # (position before the move, the move, the previous move in UCI, whether that previous move was a castling).
    positions: list[tuple[chess.Board, chess.Move, str | None, bool]] = []
    previous: str | None = None
    after_castling = False
    for move in pgn_game.mainline_moves():
        positions.append((board.copy(stack=False), move, previous, after_castling))
        previous = move.uci()
        after_castling = board.is_castling(move)
        board.push(move)

    candidates: dict[str, list[tuple[int, dict]]] = {color: [] for color in players}
    for index, item in enumerate(moves_report):
        color = item.get("color")
        if color not in players or index >= len(positions):
            continue
        if item.get("classification") not in ("Mistake", "Blunder") or int(item.get("cp_loss", 0)) < MIN_LOSS:
            continue
        if not item.get("best_move_uci") or item["best_move_uci"] == item.get("uci"):
            continue
        candidates[color].append((index, item))

    added = 0
    for color, items in candidates.items():
        user = players[color]
        chosen = 0
        for index, item in sorted(items, key=lambda pair: -int(pair[1].get("cp_loss", 0))):
            if chosen >= MAX_PER_PLAYER:
                break
            ply = index + 1
            if (user.id, ply) in existing:
                chosen += 1
                continue
            position, played, previous_move, after_castling = positions[index]
            if not readable_as_standard(position, after_castling):
                continue
            best = chess.Move.from_uci(item["best_move_uci"])
            if best not in position.legal_moves:
                continue
            try:
                with engine_work("puzzles"):
                    top = await asyncio.to_thread(top_two, position.copy(stack=False))
            except EngineUnavailableError as exc:
                logger.warning("Stockfish unavailable for puzzles from a game (%s): %s", label, exc)
                return added
            if top is None:
                return added
            if not is_solvable(position, best, top):
                continue
            db.add(PersonalPuzzle(
                user_id=user.id, ply=ply, fen=position.fen(), previous_move=previous_move,
                solution=best.uci(), played=played.uci(), cp_loss=int(item.get("cp_loss", 0)),
                themes=join_themes(themes_of(position, best)), **source,
            ))
            chosen += 1
            added += 1
    await db.commit()
    return added


# --- decision and repetition -------------------------------------------------------------------------------

def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _aware(value: dt.datetime) -> dt.datetime:
    return value if value.tzinfo else value.replace(tzinfo=dt.UTC)


def view(puzzle: PersonalPuzzle) -> dict:
    """A personal puzzle for the client: position, previous move, side to move, themes, attempt counters. No solution."""
    board = chess.Board(puzzle.fen)
    return {
        "id": puzzle.id, "game_id": puzzle.game_id, "imported_game_id": puzzle.imported_game_id,
        "ply": puzzle.ply, "fen": puzzle.fen,
        "previous_move": puzzle.previous_move, "color": "white" if board.turn == chess.WHITE else "black",
        "themes": split_themes(puzzle.themes),
        "attempts": puzzle.attempts, "solved_streak": puzzle.solved_streak,
    }


async def game_context(db: AsyncSession, puzzle: PersonalPuzzle, user: User) -> dict:
    """
    Where the mistake came from (task B.3): the opponent (a bot - its id, the client translates the name; a personality of
    its own - its name) and the game date.
    """
    if puzzle.imported_game_id is not None:
        imported = await db.get(ImportedGame, puzzle.imported_game_id)
        if imported is None:
            return {"opponent": None, "opponent_is_bot": False, "played_at": None, "source": None}
        return {
            "opponent": imported.black_name if imported.color == "white" else imported.white_name,
            "opponent_is_bot": False, "played_at": _aware(imported.played_at).isoformat() if imported.played_at else None,
            "source": imported.source,
        }
    game = await db.get(Game, puzzle.game_id) if puzzle.game_id is not None else None
    if game is None:
        return {"opponent": None, "opponent_is_bot": False, "played_at": None, "source": None}
    opponent_id = game.black_player_id if game.white_player_id == user.id else game.white_player_id
    opponent = await db.get(User, opponent_id)
    name = game.personality_name if game.personality_name and opponent is not None and opponent.is_bot else None
    when = game.finished_at or game.created_at
    return {
        "opponent": name or (opponent.username if opponent is not None else None),
        "opponent_is_bot": bool(opponent is not None and opponent.is_bot and not name),
        "played_at": _aware(when).isoformat() if when else None,
        "source": None,
    }


async def summary(db: AsyncSession, user: User) -> dict:
    """
    Summary of the player's personal puzzles: how many to repeat now, how many in progress, how many mastered and when the
    next one is due.
    """
    now = _now()
    total = await db.scalar(select(func.count()).select_from(PersonalPuzzle).where(
        PersonalPuzzle.user_id == user.id, PersonalPuzzle.done.is_(False))) or 0
    due = await db.scalar(select(func.count()).select_from(PersonalPuzzle).where(
        PersonalPuzzle.user_id == user.id, PersonalPuzzle.done.is_(False), PersonalPuzzle.due_at <= now)) or 0
    mastered = await db.scalar(select(func.count()).select_from(PersonalPuzzle).where(
        PersonalPuzzle.user_id == user.id, PersonalPuzzle.done.is_(True))) or 0
    upcoming = await db.scalar(select(func.min(PersonalPuzzle.due_at)).where(
        PersonalPuzzle.user_id == user.id, PersonalPuzzle.done.is_(False), PersonalPuzzle.due_at > now))
    return {"due": due, "active": total, "mastered": mastered,
            "next_due_at": _aware(upcoming).isoformat() if upcoming else None}


async def next_due(db: AsyncSession, user: User) -> PersonalPuzzle | None:
    """Next puzzle to repeat: not mastered, whose due time has come; the one with the oldest due time first."""
    return await db.scalar(
        select(PersonalPuzzle).where(PersonalPuzzle.user_id == user.id, PersonalPuzzle.done.is_(False),
                                     PersonalPuzzle.due_at <= _now())
        .order_by(PersonalPuzzle.due_at, PersonalPuzzle.id).limit(1)
    )


async def answer(db: AsyncSession, user: User, puzzle_id: int, uci: str) -> dict:
    """
    Answer to a personal puzzle: correct - the interval grows; wrong - again tomorrow. Solved twice in a row - mastered.
    A correct answer is the solution move or any move that gives mate. The next showing time is counted from the moment of
    the answer. The answer reveals the solution and the move made in the game - also on a wrong answer.
    """
    puzzle = await db.get(PersonalPuzzle, puzzle_id)
    if puzzle is None or puzzle.user_id != user.id:
        from src.services.puzzles import PuzzleError

        raise PuzzleError("puzzle_not_found", 404, puzzle_id=puzzle_id)
    board = chess.Board(puzzle.fen)
    try:
        move = chess.Move.from_uci(uci)
    except ValueError:
        raise DomainValueError("illegal_move", move=uci) from None
    if move not in board.legal_moves:
        raise DomainValueError("illegal_move", move=uci)
    after = board.copy(stack=False)
    after.push(move)
    correct = uci == puzzle.solution or after.is_checkmate()
    puzzle.attempts += 1
    if correct:
        puzzle.solved_streak += 1
        if puzzle.solved_streak >= SOLVES_TO_MASTER:
            puzzle.done = True
        else:
            puzzle.interval_index = min(puzzle.interval_index + 1, len(INTERVALS_DAYS) - 1)
    else:
        puzzle.solved_streak = 0
        puzzle.interval_index = 0
    puzzle.due_at = _now() + dt.timedelta(days=INTERVALS_DAYS[puzzle.interval_index])
    await db.commit()
    return {
        "correct": correct, "solution": puzzle.solution, "played": puzzle.played, "done": puzzle.done,
        "solved_streak": puzzle.solved_streak, "next_due_at": None if puzzle.done else _aware(puzzle.due_at).isoformat(),
    }


async def plies_for_game(db: AsyncSession, game_id: int, user: User | None) -> list[int]:
    """Plies of a game from which puzzles were made (for the badge in the review): own - for the game owner."""
    if user is None:
        return []
    rows = await db.execute(select(PersonalPuzzle.ply).where(PersonalPuzzle.game_id == game_id,
                                                              PersonalPuzzle.user_id == user.id))
    return sorted(set(rows.scalars()))


async def plies_for_imported(db: AsyncSession, imported_id: int, user: User) -> list[int]:
    """The same as ``plies_for_game``, for a game from another site."""
    rows = await db.execute(select(PersonalPuzzle.ply).where(PersonalPuzzle.imported_game_id == imported_id,
                                                              PersonalPuzzle.user_id == user.id))
    return sorted(set(rows.scalars()))
