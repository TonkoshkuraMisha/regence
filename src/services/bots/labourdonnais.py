# --- FILE: src/services/bots/labourdonnais.py ---
"""
Historical bot "Louis-Charles de La Bourdonnais": opening book and style rules.

Opening — a book from the prototype's games (books/labourdonnais.json, built by scripts/build_opening_books.py) and several
"signature" openings set here (DEFAULT_LABOURDONNAIS_BOOK).

Style (LABOURDONNAIS_STYLE) — bonuses in centipawns for engine candidates: quick development of minor pieces and castling,
the centre, checks and captures, after the opening — pieces towards the opponent's king and sacrifices. The bonuses only choose
among moves close
in evaluation to the best one (the window is blunder_guard_cp); they do not change the position evaluation.

Strength: the declared rating and the engine's UCI_Elo limit — 1950; the match-measured one — calibration.json. The move
selection
order is base.HistoricalBot; the bot's remarks are the botComments.labourdonnais.* catalog keys on the client.
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
LABOURDONNAIS_BLUNDER_GUARD_CP = 200.0

# Signature lines: position (FEN without move counters) → [(UCI, weight, remark key botComments.*)]. On top of the book from
# books/*.json (load_bot_opening_book): a move from the file replaces the matching one, and signature moves absent from the
# file
# are added.
DEFAULT_LABOURDONNAIS_BOOK: dict[str, list[BookEntry]] = {
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -": [
        ("e2e4", 81, "labourdonnais.bookE4"),
        ("d2d4", 16, "labourdonnais.bookD4"),
        ("f2f4", 3, "labourdonnais.bookF4"),
    ],
    "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq -": [
        ("b2b4", 86, "labourdonnais.bookEvans"),
        ("c2c3", 14, "labourdonnais.bookC3"),
    ],
}

LABOURDONNAIS_OPENING_BOOK = load_bot_opening_book("labourdonnais", DEFAULT_LABOURDONNAIS_BOOK)


LABOURDONNAIS_STYLE = Style(
    "labourdonnais",
    Rule(CASTLING, 38.0, "labourdonnais.castle"),
    Group(
        piece(*MINOR_PIECES) & by_move(12),
        Rule(FROM_BACK_RANK, 25.0, "labourdonnais.develop"),
        Rule(to(EXTENDED_CENTER), 18.0, "labourdonnais.centralize"),
    ),
    Rule(
        to(CENTER_SQUARES), 22.0,
        "labourdonnais.center", Note.FILL,
    ),
    FirstOf(
        Rule(CHECK, 24.0, "labourdonnais.check"),
        Rule(CAPTURE, 14.0),
    ),
    Group(
        after_move(12),
        Rule(NEAR_ENEMY_KING, 20.0),
        Rule(SACRIFICE, 16.0),
    ),
)
# The style evaluation function as a standalone name (bot tests import it).
evaluate_labourdonnais_style_bonus = LABOURDONNAIS_STYLE.evaluate


class LabourdonnaisBot(HistoricalBot):
    """Louis-Charles Mahe de La Bourdonnais: UCI_Elo 1950, depth 5, level 5; random spread +-12 cp, MultiPV 8."""

    bot_id = "labourdonnais"
    engine_source_name = "labourdonnais_style_engine"
    default_comment = "labourdonnais.default"
    blunder_guard_cp = LABOURDONNAIS_BLUNDER_GUARD_CP
    jitter_range = 12.0
    multipv = 8
    opening_book = LABOURDONNAIS_OPENING_BOOK
    style = LABOURDONNAIS_STYLE
    default_uci_elo = 1950
    default_search_depth = 5


labourdonnais_bot = LabourdonnaisBot()
