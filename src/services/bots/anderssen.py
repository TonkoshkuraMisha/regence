# --- FILE: src/services/bots/anderssen.py ---
"""
Historical bot "Adolf Anderssen": opening book and style rules.

Opening — a book from the prototype's games (books/anderssen.json, built by scripts/build_opening_books.py) and several
"signature" openings set here (DEFAULT_ANDERSSEN_BOOK).

Style (ANDERSSEN_STYLE) — bonuses in centipawns for engine candidates: checks, captures that open lines, development, after
the opening — sacrifices and pieces near the opponent's king (his move selection window is the widest of the seven bots). The
bonuses only
choose among moves close in evaluation to the best one (the window is blunder_guard_cp); they do not change the position
evaluation.

Strength: the declared rating and the engine's UCI_Elo limit — 2100; the match-measured one — calibration.json. The move
selection
order is base.HistoricalBot; the bot's remarks are the botComments.anderssen.* catalog keys on the client.
"""

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
    Group,
    Note,
    Rule,
    Style,
    after_move,
    by_move,
    piece,
    to,
)

# Width of the move selection window, cp (base.HistoricalBot._window): with a strength reference move the bot may fall short of
# it by at most
# half of this value, without an engine — short of the best move by at most the whole value. The wider, the more room for
# style.
ANDERSSEN_BLUNDER_GUARD_CP = 220.0

# Signature lines: position (FEN without move counters) → [(UCI, weight, remark key botComments.*)]. On top of the book from
# books/*.json (load_bot_opening_book): a move from the file replaces the matching one, and signature moves absent from the
# file
# are added.
DEFAULT_ANDERSSEN_BOOK: dict[str, list[BookEntry]] = {
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -": [
        ("e2e4", 96, "anderssen.bookGambit"),
        ("a2a3", 2, "anderssen.bookA3"),
        ("d2d4", 1, "anderssen.bookD4"),
        ("f2f4", 1, "anderssen.bookF4"),
    ],
    "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq -": [
        ("b2b4", 97, "anderssen.bookEvans"),
        ("e1g1", 2, "anderssen.bookCastle"),
        ("c2c3", 1, "anderssen.bookItalian"),
    ],
}

ANDERSSEN_OPENING_BOOK = load_bot_opening_book("anderssen", DEFAULT_ANDERSSEN_BOOK)


ANDERSSEN_STYLE = Style(
    "anderssen",
    Rule(CHECK, 36.0, "anderssen.check"),
    Rule(CAPTURE, 24.0, "anderssen.openLines", Note.FILL),
    Rule(CASTLING, 38.0, "anderssen.castle"),
    Group(
        piece(*MINOR_PIECES) & by_move(14),
        Rule(FROM_BACK_RANK, 28.0, "anderssen.develop", Note.FILL),
        Rule(to(EXTENDED_CENTER), 18.0),
    ),
    Rule(to(CENTER_SQUARES), 22.0, "anderssen.center", Note.FILL),
    Group(
        after_move(14),
        Rule(SACRIFICE, 30.0, "anderssen.openLines", Note.FILL),
        Rule(NEAR_ENEMY_KING, 18.0),
    ),
)
# The style evaluation function as a standalone name (bot tests import it).
evaluate_anderssen_style_bonus = ANDERSSEN_STYLE.evaluate


class AnderssenBot(HistoricalBot):
    """Adolf Anderssen: UCI_Elo 2100, depth 6, level 8; random spread +-10 cp, MultiPV 8."""

    bot_id = "anderssen"
    engine_source_name = "anderssen_style_engine"
    default_comment = "anderssen.default"
    blunder_guard_cp = ANDERSSEN_BLUNDER_GUARD_CP
    jitter_range = 10.0
    multipv = 8
    opening_book = ANDERSSEN_OPENING_BOOK
    style = ANDERSSEN_STYLE
    default_uci_elo = 2100


anderssen_bot = AnderssenBot()
