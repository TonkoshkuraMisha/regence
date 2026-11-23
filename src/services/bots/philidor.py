# --- FILE: src/services/bots/philidor.py ---
"""
Historical bot "Francois-Andre Philidor": opening book and style rules.

Opening — a book from the prototype's games (books/philidor.json, built by scripts/build_opening_books.py) and several
"signature" openings set here (DEFAULT_PHILIDOR_BOOK).

Style (PHILIDOR_STYLE) — bonuses in centipawns for engine candidates: pawn moves into the centre and for space ("pawns are the
soul of chess"), a knight does not stand in front of its own "c" or "f" pawn until it has moved, preserving the pawn structure.
The bonuses only choose among moves close in evaluation to the best one (the window is blunder_guard_cp); they do not
change the position evaluation.

Strength: the declared rating and the engine's UCI_Elo limit — 1850; the match-measured one — calibration.json. The move
selection
order is base.HistoricalBot; the bot's remarks are the botComments.philidor.* catalog keys on the client.
"""

import chess

from src.services.bots.base import (
    PIECE_VALUES,
    BookEntry,
    HistoricalBot,
    analyse_with_stockfish,
    load_bot_opening_book,
    normalize_fen_key,
    resolve_stockfish_path,
    static_board_eval_cp,
)
from src.services.bots.style import (
    ALWAYS,
    CENTER_SQUARES,
    EXTENDED_CENTER,
    FirstOf,
    Group,
    Rule,
    Style,
    by_move,
    pawn_structure_delta,
    piece,
    piece_on,
    side,
    to,
)

# Width of the move selection window, cp (base.HistoricalBot._window): with a strength reference move the bot may fall short of
# it by at most
# half of this value, without an engine — short of the best move by at most the whole value. The wider, the more room for
# style.
PHILIDOR_BLUNDER_GUARD_CP = 120.0

# Signature lines: position (FEN without move counters) → [(UCI, weight, remark key botComments.*)]. On top of the book from
# books/*.json (load_bot_opening_book): a move from the file replaces the matching one, and signature moves absent from the
# file
# are added.
DEFAULT_PHILIDOR_BOOK: dict[str, list[BookEntry]] = {
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -": [
        ("e2e4", 92, "philidor.bookE4"),
        ("d2d4", 8, "philidor.bookD4"),
    ],
    "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq -": [
        ("e7e5", 72, "philidor.bookE5"),
        ("c7c5", 18, "philidor.bookC5"),
        ("e7e6", 10, "philidor.bookE6"),
    ],
    "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq -": [
        ("d7d6", 100, "philidor.bookDefense"),
    ],
    "rnbqkbnr/ppp2ppp/3p4/4p3/3PP3/5N2/PPP2PPP/RNBQKB1R b KQkq -": [
        ("f7f5", 65, "philidor.bookF5"),
        ("e5d4", 35, "philidor.bookExd4"),
    ],
    "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/8/PPPP1PPP/RNBQK1NR w KQkq -": [
        ("c2c3", 100, "philidor.bookC3"),
    ],
}

PHILIDOR_OPENING_BOOK = load_bot_opening_book("philidor", DEFAULT_PHILIDOR_BOOK)
# Forced: against 1.e4 e5 2.Nf3 the bot always answers d6 (the defence of its name), even if the book from the archive games
# has other replies.
PHILIDOR_OPENING_BOOK["rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq -"] = [
    ("d7d6", 100, "philidor.bookDefense"),
]


# Pawns for the piece_on condition in the "knight not in front of the c/f pawn" rules (squares c2/f2 and c7/f7).
WHITE_PAWN = chess.Piece(chess.PAWN, chess.WHITE)
BLACK_PAWN = chess.Piece(chess.PAWN, chess.BLACK)

PHILIDOR_STYLE = Style(
    "philidor",
    Group(
        piece(chess.PAWN),
        Rule(ALWAYS, 14.0),
        FirstOf(
            Rule(to(CENTER_SQUARES), 35.0, "philidor.pawnCenter"),
            Rule(to(EXTENDED_CENTER), 22.0, "philidor.pawnSpace"),
            Rule(
                to({chess.C3, chess.C6, chess.D3, chess.D6}), 16.0,
                "philidor.pawnPrepare",
            ),
        ),
    ),
    # "A knight should not stand in front of the c pawn": a penalty for Nc3/Nf3 (Nc6/Nf6) while the pawn has not moved.
    Group(
        piece(chess.KNIGHT) & by_move(10) & side(chess.WHITE),
        Rule(to({chess.C3}) & piece_on(chess.C2, WHITE_PAWN), -55.0),
        Rule(to({chess.F3}) & piece_on(chess.F2, WHITE_PAWN), -45.0),
    ),
    Group(
        piece(chess.KNIGHT) & by_move(10) & side(chess.BLACK),
        Rule(to({chess.C6}) & piece_on(chess.C7, BLACK_PAWN), -55.0),
        Rule(to({chess.F6}) & piece_on(chess.F7, BLACK_PAWN), -45.0),
    ),
    Rule(ALWAYS, pawn_structure_delta),
)
# The style evaluation function as a standalone name (bot tests import it).
evaluate_philidor_style_bonus = PHILIDOR_STYLE.evaluate


class PhilidorBot(HistoricalBot):
    """Francois-Andre Philidor: UCI_Elo 1850, depth 6, level 7 (base class values); spread +-8 cp, MultiPV 6."""

    bot_id = "philidor"
    engine_source_name = "philidor_style_engine_deep"
    default_comment = "philidor.default"
    blunder_guard_cp = PHILIDOR_BLUNDER_GUARD_CP
    jitter_range = 8.0
    multipv = 6
    opening_book = PHILIDOR_OPENING_BOOK
    style = PHILIDOR_STYLE


philidor_bot = PhilidorBot()

# Re-export of common base functions: the old imports of tests and src/api/bots.py go through this module.
__all__ = [
    "CENTER_SQUARES",
    "EXTENDED_CENTER",
    "PIECE_VALUES",
    "PHILIDOR_OPENING_BOOK",
    "PhilidorBot",
    "philidor_bot",
    "evaluate_philidor_style_bonus",
    "analyse_with_stockfish",
    "normalize_fen_key",
    "resolve_stockfish_path",
    "static_board_eval_cp",
]
