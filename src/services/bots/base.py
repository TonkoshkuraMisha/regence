# --- FILE: src/services/bots/base.py ---
"""
The general order in which a bot chooses a move (HistoricalBot) and what it uses for that.

1. Opening: while the position is in the bot's book (books/<id>.json — move statistics from its prototype's games, built by
   scripts/build_opening_books.py, plus a few "signature" lines in the bot's module), a move is taken from it at random,
   weighted by frequency in the prototype's games and by the bot's own experience (src/services/bots/memory.py).
2. Candidates: the engine from the pool (src/services/engine_pool.py) evaluates several best moves at full strength;
   without an engine — the static analyser (fallback_scores).
3. Strength: the reference move is the one the engine would play with the bot's UCI_Elo strength limit
(strength_reference_move). The selection window
   is built around it: the bot does not play noticeably stronger or noticeably weaker than the reference move (_window).
4. Style: inside the window each move gets bonuses by the style rules (src/services/bots/style.py) and a small
   random spread; the move with the best sum is chosen. Style does not change the position evaluation.

Also here: locating the engine binary (resolve_stockfish_path: the project's bin/, PATH, standard Linux paths) and the bot's
remark
as a botComments catalog key (bot_comment) — the server does not return text. The bot answers without an artificial pause.
The bots' measured strength is calibration.json (scripts/calibrate_bots.py).

Callers: choose_move — src/api/bots.py (in a thread) and tournament simulation; the static evaluation and analysis — also
analysis_service.py and tournament_simulation.py.
"""

import json
import logging
import os
import random
import shutil
from dataclasses import dataclass
from pathlib import Path

import chess
import chess.engine

from src.services.bots import memory
from src.services.bots.style import CENTER_SQUARES, EXTENDED_CENTER, Style
from src.services.engine_pool import EngineLease, get_engine_pool

logger = logging.getLogger(__name__)


def _engine(engine_path: str, lease: EngineLease | None, options: dict):
    """The engine from the move lease if there is one, otherwise separately from the pool for a single call."""
    return lease.use(options) if lease is not None else get_engine_pool(engine_path).acquire(options)

# The package folder; books are in books/, the project root is needed to find bin/ with the engine and *_generated_book.json.
BOTS_DIR = Path(__file__).resolve().parent
BOOKS_DIR = BOTS_DIR / "books"
PROJECT_ROOT = BOTS_DIR.parent.parent.parent

# Material values for static_board_eval_cp, cp; the king is deliberately worth more than everything else.
PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20000,
}


def normalize_fen_key(board: chess.Board) -> str:
    """Key of a position for the book and memory: piece placement, side to move and castling rights; the en-passant field is
    always "-"."""
    parts = board.fen().split(" ")
    return f"{parts[0]} {parts[1]} {parts[2]} -"


def resolve_stockfish_path(custom_path: str | None = None) -> str | None:
    """Path to the engine binary: custom_path if it exists; otherwise the project's bin/, PATH, Linux paths; None — not
    found."""
    if custom_path and os.path.exists(custom_path):
        return custom_path

    for binary_name in ("stockfish.exe", "stockfish"):
        candidate = PROJECT_ROOT / "bin" / binary_name
        if candidate.exists() and candidate.is_file():
            return str(candidate)

    which_path = shutil.which("stockfish")
    if which_path:
        return which_path

    for linux_path in ("/usr/games/stockfish", "/usr/bin/stockfish", "/usr/local/bin/stockfish"):
        if os.path.exists(linux_path) and os.path.isfile(linux_path):
            return linux_path

    return None


# An opening book move: (UCI, weight, note). The note is the key of a signature bot remark (hand-made lines in code)
# or the number of archive games with this move (books from src/services/bots/books/*.json).
BookEntry = tuple[str, int, str | int]


def bot_comment(key: str, **params: int | str) -> dict:
    """
    Bot remark for the client: a botComments catalog key and parameters — the text in three languages
    is built by the client (frontend/src/i18n/messages/*.ts). The server returns no phrases.
    """
    return {"key": key, "params": params}


def load_bot_opening_book(
        bot_id: str,
        fallback_book: dict[str, list[BookEntry]] | None = None,
) -> dict[str, list[BookEntry]]:
    """
    Bot book: books/{bot_id}.json (format: position key → [[UCI, weight, number of games], ...]) or, if it is absent,
    {bot_id}_generated_book.json in the project root. For a position present both in the file and in fallback_book, the file's
    moves
    are kept, and signature moves absent from the file are added. A read error goes to the log, fallback_book remains.
    """
    book: dict[str, list[BookEntry]] = {}
    if fallback_book:
        for k, v in fallback_book.items():
            book[k] = list(v)

    candidates = [
        BOOKS_DIR / f"{bot_id}.json",
        PROJECT_ROOT / f"{bot_id}_generated_book.json",
    ]

    for json_path in candidates:
        if json_path.exists():
            try:
                with open(json_path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data:
                    for fen_key, moves in data.items():
                        parsed_moves: list[BookEntry] = [
                            (str(m[0]), int(m[1]), int(m[2]))
                            for m in moves
                            if len(m) >= 3 and str(m[0]) != "0000"
                        ]
                        if not parsed_moves:
                            continue

                        if fen_key in book:
                            existing_ucis = {m[0] for m in parsed_moves}
                            for fb_move in book[fen_key]:
                                if fb_move[0] not in existing_ucis:
                                    parsed_moves.append(fb_move)
                        book[fen_key] = parsed_moves
                    break
            except Exception as exc:
                logger.warning("Failed to load book %s: %s", json_path, exc)

    return book


def static_board_eval_cp(board: chess.Board, perspective: chess.Color) -> float:
    """Static evaluation without an engine, cp from the perspective's point of view: material and centre; mate +-100000,
    stalemate 0."""
    if board.is_checkmate():
        return -100000.0 if board.turn == perspective else 100000.0
    if board.is_stalemate() or board.is_insufficient_material():
        return 0.0

    score = 0.0
    for sq in chess.SQUARES:
        p = board.piece_at(sq)
        if not p:
            continue
        val = float(PIECE_VALUES[p.piece_type])
        if sq in CENTER_SQUARES:
            val += 25.0 if p.piece_type == chess.PAWN else 15.0
        elif sq in EXTENDED_CENTER:
            val += 15.0 if p.piece_type == chess.PAWN else 8.0

        if p.color == perspective:
            score += val
        else:
            score -= val
    return score


def fallback_scores(board: chess.Board) -> dict[chess.Move, float]:
    """Static analyser without an engine: each move is evaluated by the opponent's worst reply (2 half-moves); mate —
    100000."""
    us = board.turn
    scores: dict[chess.Move, float] = {}
    for mv in board.legal_moves:
        b1 = board.copy()
        b1.push(mv)
        if b1.is_checkmate():
            scores[mv] = 100000.0
            continue
        worst_reply_score = 100000.0
        for reply in b1.legal_moves:
            b2 = b1.copy()
            b2.push(reply)
            s = static_board_eval_cp(b2, us)
            if s < worst_reply_score:
                worst_reply_score = s
        scores[mv] = worst_reply_score if b1.legal_moves.count() > 0 else 0.0
    return scores


def analyse_with_stockfish(
        board: chess.Board,
        engine_path: str | None,
        depth: int = 6,
        time_limit: float = 0.25,
        multipv: int = 6,
        lease: EngineLease | None = None,
) -> dict[chess.Move, float]:
    """
    Evaluations of up to multipv best moves at full strength: move → cp from the mover's point of view (mate +-100000). An
    empty dict —
    no engine or it returned an error. lease is the engine leased for the whole bot move.
    """
    if not engine_path or not os.path.exists(engine_path):
        return {}

    scores: dict[chess.Move, float] = {}
    # Analysis is at full strength. UCI_LimitStrength/UCI_Elo/Skill Level weaken only the move choice in the engine's play(),
    # and do not change analyse() evaluations (verified by the 13.11 calibration, task 10.5): the bot's strength is set by the
    # reference move
    # strength_reference_move, so the analysis has no strength options.

    try:
        with _engine(engine_path, lease, {}) as engine:
            infos = engine.analyse(
                board,
                chess.engine.Limit(depth=depth, time=time_limit),
                multipv=min(multipv, board.legal_moves.count()),
            )
            if isinstance(infos, dict):
                infos = [infos]
            for info in infos:
                pv = info.get("pv")
                if pv:
                    mv = pv[0]
                    cp = info["score"].pov(board.turn).score(mate_score=100000)
                    if cp is not None:
                        scores[mv] = float(cp)
    except Exception as exc:
        logger.warning("Stockfish start error (%s): %s", engine_path, exc)
        return {}

    return scores


def strength_reference_move(
        board: chess.Board, engine_path: str | None, uci_elo: int | None, time_limit: float,
        lease: EngineLease | None = None,
) -> chess.Move | None:
    """
    The move the engine would play with the UCI_Elo strength limit (task 10.5) — the bot's strength benchmark: its weakening
    is calibrated by the engine itself. None — without an engine or without a strength limit.
    """
    if uci_elo is None or not engine_path or not os.path.exists(engine_path):
        return None
    try:
        # The pool itself brings UCI_Elo into the engine's valid range (for Stockfish — from 1320).
        with _engine(engine_path, lease, {"UCI_LimitStrength": True, "UCI_Elo": uci_elo}) as engine:
            return engine.play(board, chess.engine.Limit(time=time_limit)).move
    except Exception as exc:
        logger.warning("Stockfish reference move failed (%s): %s", engine_path, exc)
        return None


def score_move(
        board: chess.Board, engine_path: str, move: chess.Move, depth: int, time_limit: float,
        lease: EngineLease | None = None,
) -> float | None:
    """Evaluation of one move at full strength, cp for the mover (for a reference move not in MultiPV); None — failed."""
    try:
        with _engine(engine_path, lease, {}) as engine:
            info = engine.analyse(board, chess.engine.Limit(depth=depth, time=time_limit), root_moves=[move])
            cp = info["score"].pov(board.turn).score(mate_score=100000)
            return float(cp) if cp is not None else None
    except Exception as exc:
        logger.warning("Stockfish move scoring failed (%s): %s", engine_path, exc)
        return None


@dataclass
class Candidates:
    """Move candidates: evaluations (cp for the side to move), the strength reference move, whether an engine was used and
    the path to it."""

    scores: dict[chess.Move, float]
    reference: chess.Move | None
    used_engine: bool
    engine_path: str | None


# Selection window around the strength reference move: style may fall short of the reference move by up to half of
# blunder_guard_cp, but
# exceed it by at most STRENGTH_UPSIDE_CP. A symmetric window (13.11 calibration) gave aggressive
# personas with a wide window +300…+400 over the declared strength: style "corrected" a weak reference move.
STRENGTH_BAND_SHARE = 0.5
STRENGTH_UPSIDE_CP = 20.0


class HistoricalBot:
    """
    A bot with style: an opening book, then candidates from the engine (MultiPV) or the static analyser, among which style
    (src/services/bots/style.py) picks a move inside the strength window (see _window). Historical bots set only
    class attributes, a book and a style preset; personas with sliders — src/services/bots/personality.py.

    Class attributes: bot_id (key of the book, memory and remarks), engine_source_name (the source field in the response),
    default_comment (remark without a special feature), blunder_guard_cp (window width, cp), jitter_range (random
    spread +-cp), multipv (how many lines to ask the engine for), time_limit (seconds for analysis), opening_book, style,
    default_uci_elo (strength reference move), default_search_depth.
    """

    bot_id: str = "base"
    engine_source_name: str = "historical_style_engine"
    default_comment: str = "common.positional"
    blunder_guard_cp: float = 130.0
    jitter_range: float = 8.0
    multipv: int = 6
    time_limit: float = 0.25
    opening_book: dict[str, list[BookEntry]] = {}
    style: Style = Style("neutral")
    default_uci_elo: int = 1850
    default_search_depth: int = 6

    def __init__(
            self,
            stockfish_path: str | None = None,
            uci_elo: int | None = None,
            search_depth: int | None = None,
    ):
        """Strength parameters replace default_*; stockfish_path is an explicit path to the engine, otherwise it is searched
        for."""
        self._explicit_stockfish_path = stockfish_path
        self.stockfish_path = resolve_stockfish_path(stockfish_path)
        self.uci_elo: int | None = self.default_uci_elo if uci_elo is None else uci_elo
        self.search_depth = self.default_search_depth if search_depth is None else search_depth

    def _get_active_engine_path(self) -> str | None:
        """Path to the engine: explicitly given (if the file exists) or found; a lost one is searched for again. None — no
        engine."""
        if self._explicit_stockfish_path is not None:
            return self._explicit_stockfish_path if os.path.exists(self._explicit_stockfish_path) else None
        if self.stockfish_path and os.path.exists(self.stockfish_path):
            return self.stockfish_path
        self.stockfish_path = resolve_stockfish_path()
        return self.stockfish_path

    def evaluate_style_bonus(self, board_before: chess.Board, move: chess.Move) -> tuple[float, str | None]:
        """Style bonus (cp) and remark key for a move in the position before it (the bot's Style.evaluate)."""
        return self.style.evaluate(board_before, move)

    def _book_note(self, note: str | int) -> dict:
        """Remark for a book move: a signature phrase by key or "a move from archive games" with their count."""
        if isinstance(note, int):
            return bot_comment(f"book.{self.bot_id}", games=note)
        return bot_comment(note)

    def _book_move(self, board: chess.Board) -> tuple[chess.Move, dict] | None:
        """A random book move and its remark; weight is the entry weight x the memory's book_factor. None — the position is
        not in the book."""
        key = normalize_fen_key(board)
        candidates = self.opening_book.get(key)
        if not candidates:
            return None
        valid_book_moves = []
        for item in candidates:
            uci_str, weight, comment = item[0], int(item[1]), item[2]
            if uci_str == "0000":
                continue
            try:
                move = chess.Move.from_uci(uci_str)
            except ValueError:
                continue
            if move in board.legal_moves:
                # The bot's experience (task 32.1): a variation that worked in its games — more often, a losing one — less
                # often.
                factor = memory.book_factor(self.bot_id, key, uci_str)
                valid_book_moves.append((move, max(weight, 1) * factor, comment))
        if not valid_book_moves:
            return None
        moves, weights, comments = zip(*valid_book_moves, strict=True)
        idx = random.choices(range(len(moves)), weights=weights, k=1)[0]
        return moves[idx], self._book_note(comments[idx])

    def _candidate_scores(self, board: chess.Board) -> Candidates:
        """
        Candidates of MultiPV at full strength and the strength reference move (the engine's move with the UCI_Elo limit).
        Without an engine — the
        fallback_scores evaluations and no reference move.
        """
        engine_path = self._get_active_engine_path() if self.stockfish_path is not None else None
        # One engine for all steps of a move: the move gets into the pool queue once.
        # The strength correction from games with humans (task 32.1) returns the bot to its declared strength.
        uci_elo = None if self.uci_elo is None else self.uci_elo + memory.strength_offset(self.bot_id)
        with EngineLease(engine_path) as lease:
            scores = analyse_with_stockfish(
                board=board,
                engine_path=engine_path,
                depth=self.search_depth,
                time_limit=self.time_limit,
                multipv=self.multipv,
                lease=lease,
            )
            if not scores:
                return Candidates(fallback_scores(board), None, False, engine_path)
            reference = strength_reference_move(board, engine_path, uci_elo, self.time_limit, lease=lease)
            if reference is not None and reference not in scores and engine_path:
                value = score_move(board, engine_path, reference, self.search_depth, self.time_limit, lease=lease)
                if value is None:
                    reference = None
                else:
                    scores[reference] = value
        return Candidates(scores, reference, True, engine_path)

    def _window(self, scores: dict[chess.Move, float], reference: chess.Move | None) -> dict[chess.Move, float]:
        """
        Moves among which style chooses. With a reference move — not stronger than it by more than STRENGTH_UPSIDE_CP and not
        weaker by more than half of blunder_guard_cp: the bot is not stronger than the declared strength. Without a reference
        move (no engine)
        — a window from the best move.
        """
        if reference is not None and reference in scores:
            ref = scores[reference]
            band = self.blunder_guard_cp * STRENGTH_BAND_SHARE
            window = {mv: cp for mv, cp in scores.items() if ref - band <= cp <= ref + STRENGTH_UPSIDE_CP}
            window[reference] = ref
            return window
        best = max(scores.values())
        return {mv: cp for mv, cp in scores.items() if cp >= best - self.blunder_guard_cp} or scores

    def _select_move(
            self, board: chess.Board, scores: dict[chess.Move, float], reference: chess.Move | None = None,
    ) -> tuple[chess.Move, str | None]:
        """The best by the sum "evaluation + style + spread" among the strength window moves (see _window)."""
        candidate_scores = self._window(scores, reference)

        best_move = None
        best_total_score = -float("inf")
        best_comment = None
        for mv, tactical_cp in candidate_scores.items():
            style_bonus, note = self.evaluate_style_bonus(board, mv)
            jitter = random.uniform(-self.jitter_range, self.jitter_range)
            total_score = tactical_cp + style_bonus + jitter
            if total_score > best_total_score:
                best_total_score = total_score
                best_move = mv
                best_comment = note

        if best_move is None:
            best_move = next(iter(board.legal_moves))
        return best_move, best_comment

    def _comment_for(self, board: chess.Board, move: chess.Move, note: str | None) -> dict:
        """Remark for the chosen move: a key from a style rule, otherwise default_comment (board and move are for
        overrides)."""
        return bot_comment(note or self.default_comment)

    def choose_move(self, fen: str) -> dict:
        """
        The bot's move in a position: from the opening book, and when the book runs out — a style choice among engine
        candidates (the order
        is in the module description). Returns a dict: the move in UCI and SAN, the position after it, the move source and the
        bot's
        remark. ValueError — the game in the position is already over.
        """
        board = chess.Board(fen)
        if board.is_game_over():
            raise ValueError("Game is already over")

        # 1. Opening book
        book = self._book_move(board)
        if book is not None:
            chosen_move, comment = book
            san = board.san(chosen_move)
            board.push(chosen_move)
            return {
                "uci": chosen_move.uci(),
                "san": san,
                "fen_after": board.fen(),
                "source": "opening_book",
                "comment": comment,
            }

        # 2. Engine (or static analyser) candidates, 3. choice by style
        candidates = self._candidate_scores(board)
        used_stockfish, engine_path = candidates.used_engine, candidates.engine_path
        best_move, note = self._select_move(board, candidates.scores, candidates.reference)
        comment = self._comment_for(board, best_move, note)

        san = board.san(best_move)
        board.push(best_move)

        engine_backend = "stockfish" if used_stockfish else "fallback_minimax"
        logger.info(
            "Bot %s move %s via %s [%s] (engine=%s)",
            self.bot_id,
            san,
            self.engine_source_name,
            engine_backend,
            engine_path,
        )
        return {
            "uci": best_move.uci(),
            "san": san,
            "fen_after": board.fen(),
            "source": self.engine_source_name,
            "engine_backend": engine_backend,
            "comment": comment,
        }
