# --- FILE: src/services/bots/staunton.py ---
"""
Historical bot "Howard Staunton": opening book and style rules.

Opening — a book from the prototype's games (books/staunton.json, built by scripts/build_opening_books.py) and several
"signature" openings set here (DEFAULT_STAUNTON_BOOK).

Style (STAUNTON_STYLE) — bonuses in centipawns for engine candidates: flank control of the centre with the "c" pawn,
development and
castling, after the opening — prophylaxis and preserving the pawn structure. The bonuses only choose among moves close
in evaluation to the best one (the window is blunder_guard_cp); they do not change the position evaluation.

Strength: the declared rating and the engine's UCI_Elo limit — 2000; the match-measured one — calibration.json. The move
selection
order is base.HistoricalBot; the bot's remarks are the botComments.staunton.* catalog keys on the client.
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
    FROM_BACK_RANK,
    MINOR_PIECES,
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
STAUNTON_BLUNDER_GUARD_CP = 110.0

# Signature lines: position (FEN without move counters) → [(UCI, weight, remark key botComments.*)]. On top of the book from
# books/*.json (load_bot_opening_book): a move from the file replaces the matching one, and signature moves absent from the
# file
# are added.
DEFAULT_STAUNTON_BOOK: dict[str, list[BookEntry]] = {
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -": [
        ("e2e4", 82, "staunton.bookE4"),
        ("c2c4", 12, "staunton.bookC4"),
        ("d2d4", 6, "staunton.bookD4"),
    ],
    "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq -": [
        ("c7c5", 52, "staunton.bookSicilian"),
        ("e7e5", 38, "staunton.bookE5"),
        ("e7e6", 10, "staunton.bookFrench"),
    ],
}

STAUNTON_OPENING_BOOK = load_bot_opening_book("staunton", DEFAULT_STAUNTON_BOOK)


STAUNTON_STYLE = Style(
    "staunton",
    Rule(
        CASTLING, 40.0,
        "staunton.castle",
    ),
    Group(
        piece(chess.PAWN) & by_move(12),
        FirstOf(
            Rule(to({chess.C4, chess.C5}), 30.0, "staunton.flankControl"),
            Rule(to(CENTER_SQUARES), 24.0, "staunton.center"),
        ),
    ),
    Group(
        piece(*MINOR_PIECES) & by_move(12),
        Rule(FROM_BACK_RANK, 26.0, "staunton.develop", Note.FILL),
        Rule(to(EXTENDED_CENTER), 16.0),
    ),
    FirstOf(
        Rule(CHECK, 18.0, "staunton.check", Note.FILL),
        Rule(CAPTURE, 14.0),
    ),
    Group(
        after_move(12),
        Rule(QUIET, prophylaxis),
        Rule(ALWAYS, pawn_structure_delta),
    ),
)
# The style evaluation function as a standalone name (bot tests import it).
evaluate_staunton_style_bonus = STAUNTON_STYLE.evaluate


class StauntonBot(HistoricalBot):
    """Howard Staunton: UCI_Elo 2000, depth 6, level 7; random spread +-6 cp, MultiPV 6."""

    bot_id = "staunton"
    engine_source_name = "staunton_style_engine"
    default_comment = "staunton.default"
    blunder_guard_cp = STAUNTON_BLUNDER_GUARD_CP
    jitter_range = 6.0
    multipv = 6
    opening_book = STAUNTON_OPENING_BOOK
    style = STAUNTON_STYLE
    default_uci_elo = 2000


staunton_bot = StauntonBot()
