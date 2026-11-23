# --- FILE: src/services/analysis_service.py ---
"""
Engine analysis of a game: evaluation of every move, classification, accuracy of each side.

How it is computed: the game is walked move by move, the position before and after the move is evaluated by Stockfish from the
pool
(src/services/engine_pool.py; depth 10, at most 0.06 s per position, the evaluation is clamped to +-2000 centipawns);
if the binary is missing or fails to start — by the static evaluator (static_board_eval_cp from bots/base.py). The
move's loss in centipawns gives a class: up to 10 or the move matched the engine's first line — best, up to 45 — good, up to 95
—
inaccuracy (?!), up to 199 — mistake (?), from 200 — blunder (??). A side's accuracy (0-100 %) is the mean of the accuracies of
its moves (calculate_move_accuracy). Coach comments (src/services/coach.py) are added to the moves — only
when a real engine did the computing.

Where it is stored: the finished analysis is games.analysis_json; it is valid while the format version
(ANALYSIS_FORMAT_VERSION) and the move count match. It is computed in the background after the game (src/worker/tasks.py) or on
a button press.
Analysis of a game in progress is forbidden — it would work as a hint (GameNotFinishedError). Games from other sites
are analysed by evaluate_pgn, and their analysis is saved by the calling module (src/services/game_import.py).

Also here: the entry point for the coach's advice, hint and move check (AnalysisService.advise / hint / check_move),
which use the shared evaluation cache src/services/move_check.py.
"""

import asyncio
import contextlib
import json
import logging
import math
import os

import chess
import chess.engine
import chess.pgn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DomainError, DomainValueError
from src.models.game import Game, GameStatus
from src.services import move_check
from src.services.bots.base import resolve_stockfish_path, static_board_eval_cp
from src.services.coach import comment_for_move
from src.services.engine_pool import EngineUnavailableError, get_engine_pool
from src.services.game_engine import board_from_start_fen, read_pgn_game

logger = logging.getLogger(__name__)


def classify_move_by_cp_loss(cp_loss: int, is_best_move: bool = False) -> tuple[str, str]:
    """
    Classifies a move by centipawn loss (cp_loss):
    - Best: 0..10 cp (or an exact match with the engine's first line)
    - Good: 11..45 cp
    - Inaccuracy (?!): 46..95 cp
    - Mistake (?): 96..199 cp
    - Blunder (??): >= 200 cp
    Returns a pair (class name, sign): the sign of the best move is "!", of a good move — an empty string.
    """
    loss = max(0, int(cp_loss))
    if is_best_move or loss <= 10:
        return "Best", "!"
    if loss <= 45:
        return "Good", ""
    if loss <= 95:
        return "Inaccuracy", "?!"
    if loss < 200:
        return "Mistake", "?"
    return "Blunder", "??"


def calculate_move_accuracy(cp_loss: int) -> float:
    """
    Single-move accuracy formula (0..100%) based on centipawn loss: a decaying exponential, 0 cp — 100 %, 100 cp —
    about 66 %, 200 cp — about 43 %.
    """
    loss = max(0.0, float(cp_loss))
    raw = 103.1668 * math.exp(-0.004 * loss) - 3.1669
    return round(max(0.0, min(100.0, raw)), 1)


def calculate_accuracy(cp_losses: list[int]) -> float:
    """
    Computes a player's overall accuracy in a game (0..100%) from the list of centipawn losses: the arithmetic mean of the
    accuracies
    of individual moves. An empty list (the side had no moves) — 100.
    """
    if not cp_losses:
        return 100.0
    per_move = [calculate_move_accuracy(loss) for loss in cp_losses]
    return round(sum(per_move) / len(per_move), 1)


PHASES = ("opening", "middlegame", "endgame")
# Opening — the first 10 moves (by board move number) while the board is not yet an endgame. Endgame is one of two things:
# no queens and each side has at most 8 points of pieces — a rook with a minor piece
# (src/services/positional.is_endgame), or both sides' pieces together are at most ENDGAME_TOTAL_MATERIAL points
# (26 — for example, two rooks and a minor piece per side). Points — positional.PIECE_POINTS: knight and bishop — 3,
# rook — 5, queen — 9; pawns and kings are not counted. Everything else is middlegame.
OPENING_MOVES = 10
ENDGAME_TOTAL_MATERIAL = 26


def game_phase(board: chess.Board) -> str:
    """Game phase in the position before the move: a code from PHASES. The endgame check goes first, before move counting."""
    from src.services.positional import PIECE_POINTS, is_endgame

    total = sum(len(board.pieces(pt, color)) * points
                for pt, points in PIECE_POINTS.items() for color in chess.COLORS)
    if is_endgame(board) or total <= ENDGAME_TOTAL_MATERIAL:
        return "endgame"
    return "opening" if board.fullmove_number <= OPENING_MOVES else "middlegame"


def format_eval_display(eval_white_cp: int, mate_white: int | None = None) -> str:
    """Formats an evaluation from White's point of view for the EvalBar scale (+1.4, -0.8, M3, -M2)."""
    if mate_white is not None and mate_white != 0:
        return f"M{mate_white}" if mate_white > 0 else f"-M{abs(mate_white)}"
    pawns = eval_white_cp / 100.0
    sign = "+" if pawns > 0 else ""
    return f"{sign}{pawns:.1f}"


# Version of the analysis_json format. 2 — every move has a coach comment ("coach", task 11.2). A cache of a different
# version is considered stale and is recomputed on the next analysis request.
ANALYSIS_FORMAT_VERSION = 2


def attach_coach_comments(start_board: chess.Board, moves_report: list[dict], best_moves_uci: list[str | None]) -> None:
    """
    Coach comments for the analysis moves (in place, in moves_report[i]["coach"]). best_moves_uci[i] is the engine's best move
    in the position before move i, best_moves_uci[i + 1] is the opponent's best reply after it.
    """
    board = start_board.copy(stack=False)
    for idx, item in enumerate(moves_report):
        move = chess.Move.from_uci(item["uci"])
        reply = best_moves_uci[idx + 1] if idx + 1 < len(best_moves_uci) else None
        item["coach"] = comment_for_move(board, move, item["best_move_uci"], reply, item["classification"])
        board.push(move)


def _evaluate_board_sequence_sync(pgn_text: str, depth: int = 10) -> dict:
    """
    Synchronous pass over all positions of the game with Stockfish or the static fallback evaluator; called in a separate
    thread (evaluate_pgn). The engine is taken from the pool once for the whole game and returned to the pool when the pass
    ends.
    Returns a report: format version, engine name, side totals ("white", "black") and a list of moves ("moves") with the
    evaluation
    after the move, loss, class, phase and coach comment. An unreadable PGN — DomainValueError pgn_parse_failed.
    """
    pgn_game = read_pgn_game(pgn_text)
    if pgn_game is None:
        raise DomainValueError("pgn_parse_failed")

    board = pgn_game.board()
    start_board = board.copy(stack=False)
    mainline_moves = list(pgn_game.mainline_moves())

    sf_path = resolve_stockfish_path()
    engine = None
    engine_label = "Static Fallback Evaluator"
    engine_stack = contextlib.ExitStack()

    if sf_path and os.path.exists(sf_path):
        # EngineBusyError is deliberately not caught: under load it is better to return 503 than to
        # cache in the DB an analysis made by the static evaluator instead of Stockfish.
        try:
            engine = engine_stack.enter_context(get_engine_pool(sf_path).acquire())
            engine_label = engine.id.get("name", "Stockfish")
        except EngineUnavailableError as exc:
            logger.warning("Failed to start Stockfish (%s), using fallback: %s", sf_path, exc)
            engine = None

    # Evaluations of each position from White's point of view (index 0 = starting position)
    evals_white_cp: list[int] = []
    mates_white: list[int | None] = []
    best_moves_uci: list[str | None] = []

    def eval_single_board(b: chess.Board) -> tuple[int, int | None, str | None]:
        """
        Evaluation of one position for White: centipawns, "mate in N" (or None) and the best move. Mate and game end are
        determined
        without the engine (mate on the board — +-10000 and "mate" +-1, draw — 0); otherwise the engine computes, and without
        it or on its failure
        at this position — the static evaluator (the best move is the one after which the static evaluation is higher).
        """
        if b.is_checkmate():
            mate_val = -1 if b.turn == chess.WHITE else 1
            cp_val = -10000 if b.turn == chess.WHITE else 10000
            return cp_val, mate_val, None
        if b.is_game_over():
            return 0, None, None

        if engine is not None:
            try:
                info = engine.analyse(b, chess.engine.Limit(depth=depth, time=0.06))
                if isinstance(info, list):
                    info = info[0]
                pov_white = info["score"].white()
                mate = pov_white.mate()
                cp = pov_white.score(mate_score=10000) or 0
                cp = max(-2000, min(2000, int(cp)))
                pv = info.get("pv")
                best_uci = pv[0].uci() if pv else None
                return cp, mate, best_uci
            except Exception:
                pass

        # Fallback without the Stockfish binary
        best_uci = None
        best_side_score = -100000.0
        for candidate in b.legal_moves:
            b_copy = b.copy()
            b_copy.push(candidate)
            sc = static_board_eval_cp(b_copy, b.turn)
            if sc > best_side_score:
                best_side_score = sc
                best_uci = candidate.uci()

        white_cp = int(static_board_eval_cp(b, chess.WHITE))
        white_cp = max(-2000, min(2000, white_cp))
        return white_cp, None, best_uci

    try:
        cp0, mate0, best0 = eval_single_board(board)
        evals_white_cp.append(cp0)
        mates_white.append(mate0)
        best_moves_uci.append(best0)

        san_list: list[str] = []
        uci_list: list[str] = []
        colors: list[str] = []
        move_numbers: list[int] = []
        phases: list[str] = []

        for mv in mainline_moves:
            colors.append("white" if board.turn == chess.WHITE else "black")
            # The move number is taken from the board: a game from an arbitrary position may start
            # not with the first move and with a Black move.
            move_numbers.append(board.fullmove_number)
            phases.append(game_phase(board))
            san_list.append(board.san(mv))
            uci_list.append(mv.uci())
            board.push(mv)
            cp_i, mate_i, best_i = eval_single_board(board)
            evals_white_cp.append(cp_i)
            mates_white.append(mate_i)
            best_moves_uci.append(best_i)
    finally:
        engine_stack.close()  # returns the engine to the pool

    moves_report: list[dict] = []
    white_losses: list[int] = []
    black_losses: list[int] = []

    counts = {
        "white": {"Best": 0, "Good": 0, "Inaccuracy": 0, "Mistake": 0, "Blunder": 0},
        "black": {"Best": 0, "Good": 0, "Inaccuracy": 0, "Mistake": 0, "Blunder": 0},
    }

    for idx, uci_played in enumerate(uci_list):
        mover_color = colors[idx]
        before_white_cp = evals_white_cp[idx]
        after_white_cp = evals_white_cp[idx + 1]
        after_mate = mates_white[idx + 1]
        recommended_uci = best_moves_uci[idx]

        if mover_color == "white":
            cp_loss = max(0, before_white_cp - after_white_cp)
        else:
            cp_loss = max(0, after_white_cp - before_white_cp)

        is_exact_best = recommended_uci is not None and recommended_uci == uci_played
        if is_exact_best:
            cp_loss = 0
        # For accuracy — the same loss as in the single-move analysis: the engine's best move loses nothing, even if the
        # evaluations
        # of neighbouring positions diverged because of depth (such noise used to lower accuracy).
        (white_losses if mover_color == "white" else black_losses).append(cp_loss)

        label, symbol = classify_move_by_cp_loss(cp_loss, is_best_move=is_exact_best)
        counts[mover_color][label] += 1

        moves_report.append({
            "ply": idx + 1,
            "move_number": move_numbers[idx],
            "color": mover_color,
            "san": san_list[idx],
            "uci": uci_played,
            "eval_cp": after_white_cp,
            "eval_display": format_eval_display(after_white_cp, after_mate),
            "mate": after_mate,
            "best_move_uci": recommended_uci,
            "cp_loss": cp_loss,
            "classification": label,
            "symbol": symbol,
            "phase": phases[idx],
        })

    def phase_accuracy(color: str) -> dict[str, float | None]:
        """A side's accuracy by phase (task B.5); a phase without its moves — None."""
        result: dict[str, float | None] = {}
        for phase in PHASES:
            losses = [m["cp_loss"] for m in moves_report if m["color"] == color and m["phase"] == phase]
            result[phase] = calculate_accuracy(losses) if losses else None
        return result

    def build_side_summary(losses: list[int], side_counts: dict[str, int], color: str) -> dict:
        """Side total: accuracy for the game and by phase, number of moves of each class and the average loss in centipawns."""
        avg_loss = round(sum(losses) / len(losses), 1) if losses else 0.0
        return {
            "accuracy": calculate_accuracy(losses),
            "phases": phase_accuracy(color),
            "best": side_counts["Best"],
            "good": side_counts["Good"],
            "inaccuracies": side_counts["Inaccuracy"],
            "mistakes": side_counts["Mistake"],
            "blunders": side_counts["Blunder"],
            "avg_cp_loss": avg_loss,
        }

    # The coach explains moves only from a real engine's evaluation: the static evaluator's "best move"
    # is sometimes bad, and advice must not be based on it.
    if engine is not None:
        attach_coach_comments(start_board, moves_report, best_moves_uci)
    else:
        for item in moves_report:
            item["coach"] = None

    return {
        "format_version": ANALYSIS_FORMAT_VERSION,
        "engine": engine_label,
        "white": build_side_summary(white_losses, counts["white"], "white"),
        "black": build_side_summary(black_losses, counts["black"], "black"),
        "moves": moves_report,
    }


class GameNotFinishedError(DomainError):
    """Analysis of a game in progress is forbidden: it would work as an engine hint for the players."""


class GameDataNotFoundError(DomainError, LookupError):
    """The game or its PGN does not exist."""


_FINISHED_STATUSES = (GameStatus.COMPLETED, GameStatus.ABORTED)


def ensure_game_finished(game: Game) -> None:
    """Raises GameNotFinishedError (game_not_finished) if the game is neither finished nor aborted."""
    if game.status not in _FINISHED_STATUSES:
        raise GameNotFinishedError("game_not_finished", game_id=game.id)


def _count_mainline_plies(pgn_text: str) -> int:
    """Number of half-moves in the PGN main line; -1 for an unreadable PGN — no saved analysis will match it."""
    pgn_game = read_pgn_game(pgn_text)
    if pgn_game is None:
        return -1
    return sum(1 for _ in pgn_game.mainline_moves())


def is_current_analysis(data: object, pgn_text: str) -> bool:
    """The cache is usable: the current format version and as many moves as in the game's final PGN."""
    return (
        isinstance(data, dict)
        and data.get("format_version") == ANALYSIS_FORMAT_VERSION
        and isinstance(data.get("moves"), list)
        and len(data["moves"]) == _count_mainline_plies(pgn_text)
    )


async def evaluate_pgn(pgn_text: str) -> dict:
    """Full analysis of a PGN outside the games table (games from other sites, task 24.1); the engine comes from the pool."""
    return await asyncio.to_thread(_evaluate_board_sequence_sync, pgn_text, 10)


class AnalysisService:
    """
    On-demand analysis: position evaluation, advice, hint, move check and full game analysis. The single instance
    is analysis_service at the end of the module.
    """
    async def analyze_position(self, db: AsyncSession, moves: list[str], start_fen: str | None = None) -> dict:
        """
        Evaluation of the position after a list of moves (SAN or UCI) from the standard setup or from start_fen: evaluation for
        White and
        the best move. The first unreadable or impossible move ends the list — the position before it is evaluated. Computed by
        Stockfish from the pool (depth 10, up to 0.1 s); without the engine — a static evaluation without a best move. A busy
        pool
        (EngineBusyError) is not caught — the route responds with a refusal. The db parameter is not used.
        """
        board = board_from_start_fen(start_fen)  # InvalidStartPositionError for an impossible position
        for move_str in moves:
            try:
                board.push_san(move_str)
            except ValueError:
                try:
                    board.push_uci(move_str)
                except ValueError:
                    break

        sf_path = resolve_stockfish_path()
        eval_cp = int(static_board_eval_cp(board, chess.WHITE))
        best_move = None

        if sf_path and not board.is_game_over():  # resolve_stockfish_path has already checked the file
            def _run_pos():
                with get_engine_pool(sf_path).acquire() as eng:
                    info = eng.analyse(board, chess.engine.Limit(depth=10, time=0.1))
                    if isinstance(info, list):
                        info = info[0]
                    cp = info["score"].white().score(mate_score=10000) or 0
                    pv = info.get("pv")
                    return int(cp), (pv[0].uci() if pv else None)

            try:
                eval_cp, best_move = await asyncio.to_thread(_run_pos)
            except EngineUnavailableError as exc:
                logger.warning("Stockfish unavailable, returning static evaluation: %s", exc)

        return {
            "fen": board.fen(),
            "evaluation_cp": eval_cp,
            "evaluation_pawns": round(eval_cp / 100.0, 2),
            "best_move": best_move,
        }

    async def advise(self, fen: str) -> dict:
        """Coach advice for a position (task 11.2); the evaluation comes from the shared cache (src/services/move_check.py)."""
        return await move_check.advise(fen)

    async def hint(self, fen: str, step: int) -> dict:
        """Tiered hint (task 11.4)."""
        return await move_check.hint(fen, step)

    async def check_move(self, fen: str, move_uci: str) -> dict:
        """Move check in a game with the coach (task 11.3)."""
        return await move_check.check_move(fen, move_uci)

    async def analyze_full_game(self, db: AsyncSession, game_id: int, force: bool = False) -> dict:
        """
        Full analysis of a finished game. A ready analysis is taken from games.analysis_json if it is current
        (is_current_analysis) and no recomputation is requested; otherwise the game is analysed again and the result is saved.
        A game
        in progress is refused with GameNotFinishedError.
        """
        result = await db.execute(select(Game).where(Game.id == game_id))
        game = result.scalars().first()
        if not game or not game.pgn:
            raise GameDataNotFoundError("pgn_not_found", game_id=game_id)
        ensure_game_finished(game)

        # If the analysis is already stored in the DB and no recomputation is requested — return instantly from the cache
        cached_raw = getattr(game, "analysis_json", None)
        if cached_raw and not force:
            try:
                cached_data = json.loads(cached_raw)
                if is_current_analysis(cached_data, game.pgn):
                    cached_data["game_id"] = game_id
                    return cached_data
                # The cache does not match the final PGN (for example, saved for an unfinished game
                # before the ban on analysing games in progress) — recompute.
            except Exception:
                pass

        report = await evaluate_pgn(game.pgn)
        report["game_id"] = game_id

        if hasattr(game, "analysis_json"):
            try:
                game.analysis_json = json.dumps(report, ensure_ascii=False)
                await db.commit()
            except Exception as exc:
                await db.rollback()
                logger.warning("Failed to save the analysis cache to the DB: %s", exc)

        return report


analysis_service = AnalysisService()
