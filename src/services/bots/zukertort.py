# --- FILE: src/services/bots/zukertort.py ---
"""
Historical bot "Johannes Zukertort": opening book and style rules.

Opening — a book from the prototype's games (books/zukertort.json, built by scripts/build_opening_books.py) and several
"signature" openings set here (DEFAULT_ZUKERTORT_BOOK).

Style (ZUKERTORT_STYLE) — bonuses in centipawns for engine candidates: development and castling, the centre, checks, after the
opening —
moderate pressure on the opponent's king. The bonuses only choose among moves close in evaluation to the best one (the window —
blunder_guard_cp); they do not change the position evaluation.

Strength: the declared rating and the engine's UCI_Elo limit — 2120; the match-measured one — calibration.json. The move
selection
order is base.HistoricalBot; the bot's remarks are the botComments.zukertort.* catalog keys on the client.
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
    FirstOf,
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
ZUKERTORT_BLUNDER_GUARD_CP = 140.0

# Signature lines: position (FEN without move counters) → [(UCI, weight, remark key botComments.*)]. On top of the book from
# books/*.json (load_bot_opening_book): a move from the file replaces the matching one, and signature moves absent from the
# file
# are added.
DEFAULT_ZUKERTORT_BOOK: dict[str, list[BookEntry]] = {
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -": [
        ("e2e4", 72, "zukertort.bookE4"),
        ("g1f3", 16, "zukertort.bookNf3"),
        ("d2d4", 12, "zukertort.bookD4"),
    ],
    "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq -": [
        ("e7e5", 75, "zukertort.bookE5"),
        ("c7c5", 15, "zukertort.bookSicilian"),
        ("e7e6", 10, "zukertort.bookFrench"),
    ],
}

ZUKERTORT_OPENING_BOOK = load_bot_opening_book("zukertort", DEFAULT_ZUKERTORT_BOOK)


ZUKERTORT_STYLE = Style(
    "zukertort",
    Rule(CASTLING, 40.0, "zukertort.castle"),
    Group(
        piece(*MINOR_PIECES) & by_move(14),
        Rule(FROM_BACK_RANK, 28.0, "zukertort.develop"),
        Rule(to(EXTENDED_CENTER), 18.0),
    ),
    Rule(to(CENTER_SQUARES), 22.0, "zukertort.center", Note.FILL),
    FirstOf(
        Rule(
            CHECK, 26.0,
            "zukertort.check",
        ),
        Rule(CAPTURE, 16.0),
    ),
    Group(
        after_move(14),
        Rule(NEAR_ENEMY_KING, 14.0),
        Rule(SACRIFICE, 12.0),
    ),
)
# The style evaluation function as a standalone name (bot tests import it).
evaluate_zukertort_style_bonus = ZUKERTORT_STYLE.evaluate


class ZukertortBot(HistoricalBot):
    """Johannes Zukertort: UCI_Elo 2120, depth 6, level 8; random spread +-8 cp, MultiPV 8."""

    bot_id = "zukertort"
    engine_source_name = "zukertort_style_engine"
    default_comment = "zukertort.default"
    blunder_guard_cp = ZUKERTORT_BLUNDER_GUARD_CP
    jitter_range = 8.0
    multipv = 8
    opening_book = ZUKERTORT_OPENING_BOOK
    style = ZUKERTORT_STYLE
    default_uci_elo = 2120


zukertort_bot = ZukertortBot()
