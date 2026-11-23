# --- FILE: src/services/bots/paulsen.py ---
"""
Historical bot "Louis Paulsen": opening book and style rules.

Opening — a book from the prototype's games (books/paulsen.json, built by scripts/build_opening_books.py) and several
"signature" openings set here (DEFAULT_PAULSEN_BOOK).

Style (PAULSEN_STYLE) — bonuses in centipawns for engine candidates: a flexible pawn structure without early occupation of the
centre, bishops on the long diagonals, prophylaxis and preserving the structure. The bonuses only choose among moves close
in evaluation to the best one (the window is blunder_guard_cp); they do not change the position evaluation.

Strength: the declared rating and the engine's UCI_Elo limit — 2080; the match-measured one — calibration.json. The move
selection
order is base.HistoricalBot; the bot's remarks are the botComments.paulsen.* catalog keys on the client.
"""

import chess

from src.services.bots.base import BookEntry, HistoricalBot, load_bot_opening_book
from src.services.bots.style import (
    ALWAYS,
    CAPTURE,
    CASTLING,
    CENTER_SQUARES,
    CHECK,
    EXTENDED_CENTER,
    QUIET,
    FirstOf,
    Group,
    Note,
    Rule,
    Style,
    after_move,
    by_move,
    pawn_structure_delta,
    piece,
    prophylaxis,
    to,
)

# Width of the move selection window, cp (base.HistoricalBot._window): with a strength reference move the bot may fall short of
# it by at most
# half of this value, without an engine — short of the best move by at most the whole value. The wider, the more room for
# style.
PAULSEN_BLUNDER_GUARD_CP = 110.0

# Signature lines: position (FEN without move counters) → [(UCI, weight, remark key botComments.*)]. On top of the book from
# books/*.json (load_bot_opening_book): a move from the file replaces the matching one, and signature moves absent from the
# file
# are added.
DEFAULT_PAULSEN_BOOK: dict[str, list[BookEntry]] = {
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -": [
        ("e2e4", 90, "paulsen.bookE4"),
        ("d2d4", 6, "paulsen.bookD4"),
        ("c2c4", 4, "paulsen.bookFlank"),
    ],
    "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq -": [
        ("c7c5", 48, "paulsen.bookSicilian"),
        ("e7e5", 38, "paulsen.bookE5"),
        ("e7e6", 10, "paulsen.bookFrench"),
        ("d7d6", 4, "paulsen.bookPirc"),
    ],
}

PAULSEN_OPENING_BOOK = load_bot_opening_book("paulsen", DEFAULT_PAULSEN_BOOK)


PAULSEN_STYLE = Style(
    "paulsen",
    Rule(CASTLING, 40.0, "paulsen.castle"),
    Group(
        piece(chess.PAWN) & by_move(14),
        FirstOf(
            Rule(
                to({chess.C5, chess.E6, chess.D6, chess.A6, chess.B6, chess.G6}), 24.0,
                "paulsen.structure",
            ),
            Rule(to(CENTER_SQUARES), 20.0, "paulsen.center"),
        ),
    ),
    Group(
        piece(chess.BISHOP),
        FirstOf(
            Rule(
                to({chess.G2, chess.B2, chess.G7, chess.B7, chess.E2, chess.E7}), 26.0,
                "paulsen.bishop",
            ),
            Rule(to(EXTENDED_CENTER), 18.0),
        ),
    ),
    Rule(piece(chess.KNIGHT) & to(EXTENDED_CENTER), 16.0, "paulsen.knightCenter", Note.FILL),
    FirstOf(
        Rule(CHECK, 18.0),
        Rule(CAPTURE, 14.0),
    ),
    Group(
        after_move(14),
        Rule(QUIET, prophylaxis),
        Rule(ALWAYS, pawn_structure_delta),
    ),
)
# The style evaluation function as a standalone name (bot tests import it).
evaluate_paulsen_style_bonus = PAULSEN_STYLE.evaluate


class PaulsenBot(HistoricalBot):
    """Louis Paulsen: UCI_Elo 2080, depth 6, level 8; random spread +-6 cp, MultiPV 6."""

    bot_id = "paulsen"
    engine_source_name = "paulsen_style_engine"
    default_comment = "paulsen.default"
    blunder_guard_cp = PAULSEN_BLUNDER_GUARD_CP
    jitter_range = 6.0
    multipv = 6
    opening_book = PAULSEN_OPENING_BOOK
    style = PAULSEN_STYLE
    default_uci_elo = 2080


paulsen_bot = PaulsenBot()
