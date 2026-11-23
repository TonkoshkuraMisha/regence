# --- FILE: src/services/bots/morphy.py ---
"""
Historical bot "Paul Morphy": opening book and style rules.

Opening — a book from the prototype's games (books/morphy.json, built by scripts/build_opening_books.py) and several
"signature" openings set here (DEFAULT_MORPHY_BOOK).

Style (MORPHY_STYLE) — bonuses in centipawns for engine candidates: early castling and development of all pieces, rooks to the
central files, an open centre, then an attack on the king. The bonuses only choose among moves close in evaluation
to the best one (the window is blunder_guard_cp); they do not change the position evaluation.

Strength: the declared rating and the engine's UCI_Elo limit — 2150; the match-measured one — calibration.json. The move
selection
order is base.HistoricalBot; the bot's remarks are the botComments.morphy.* catalog keys on the client.
"""

import chess

from src.services.bots.base import BookEntry, HistoricalBot, load_bot_opening_book
from src.services.bots.style import (
    CAPTURE,
    CASTLING,
    CENTER_SQUARES,
    CHECK,
    EXTENDED_CENTER,
    FROM_BACK_RANK,
    MINOR_PIECES,
    NEAR_ENEMY_KING,
    SACRIFICE,
    FirstOf,
    Group,
    Note,
    Rule,
    Style,
    after_move,
    by_move,
    piece,
    to,
    to_file,
)

# Width of the move selection window, cp (base.HistoricalBot._window): with a strength reference move the bot may fall short of
# it by at most
# half of this value, without an engine — short of the best move by at most the whole value. The wider, the more room for
# style.
MORPHY_BLUNDER_GUARD_CP = 150.0

# Signature lines: position (FEN without move counters) → [(UCI, weight, remark key botComments.*)]. On top of the book from
# books/*.json (load_bot_opening_book): a move from the file replaces the matching one, and signature moves absent from the
# file
# are added.
DEFAULT_MORPHY_BOOK: dict[str, list[BookEntry]] = {
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -": [
        ("e2e4", 94, "morphy.bookE4"),
        ("d2d4", 6, "morphy.bookD4"),
    ],
    "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq -": [
        ("b2b4", 82, "morphy.bookEvans"),
        ("c2c3", 12, "morphy.bookC3"),
        ("e1g1", 6, "morphy.bookCastle"),
    ],
    "rnbqkbnr/ppp2ppp/3p4/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq -": [
        ("d2d4", 100, "morphy.bookOpera"),
    ],
}

MORPHY_OPENING_BOOK = load_bot_opening_book("morphy", DEFAULT_MORPHY_BOOK)


MORPHY_STYLE = Style(
    "morphy",
    Rule(CASTLING, 45.0, "morphy.castle"),
    Group(
        piece(*MINOR_PIECES) & by_move(14),
        Rule(
            FROM_BACK_RANK, 32.0,
            "morphy.develop",
        ),
        Rule(to(EXTENDED_CENTER), 18.0, "morphy.centralize", Note.FILL),
    ),
    Rule(piece(chess.ROOK) & to_file(3, 4), 26.0, "morphy.rookFile"),
    Rule(to(CENTER_SQUARES), 24.0, "morphy.openCenter", Note.FILL),
    FirstOf(
        Rule(CHECK, 28.0, "morphy.check"),
        Rule(CAPTURE, 16.0, "morphy.capture", Note.FILL),
    ),
    Group(
        after_move(14),
        Rule(NEAR_ENEMY_KING, 16.0, "morphy.kingAttack", Note.FILL),
        Rule(SACRIFICE, 12.0),
    ),
)
# The style evaluation function as a standalone name (bot tests import it).
evaluate_morphy_style_bonus = MORPHY_STYLE.evaluate


class MorphyBot(HistoricalBot):
    """Paul Morphy: UCI_Elo 2150, depth 6, level 8; random spread +-8 cp, MultiPV 8."""

    bot_id = "morphy"
    engine_source_name = "morphy_style_engine"
    default_comment = "morphy.default"
    blunder_guard_cp = MORPHY_BLUNDER_GUARD_CP
    jitter_range = 8.0
    multipv = 8
    opening_book = MORPHY_OPENING_BOOK
    style = MORPHY_STYLE
    default_uci_elo = 2150


morphy_bot = MorphyBot()
