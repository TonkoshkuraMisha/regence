"""
Historical masters (task 21.5): Steinitz, Lasker, Rubinstein, Capablanca, Alekhine, then Chigorin, Tarrasch,
Pillsbury, Marshall, Nimzowitsch, Reti, Tartakower, Botvinnik, Tal, Petrosian — deceased chess players (rule 1; the last
three — owner decision of 16.11), portraits under a free licence (ATTRIBUTION.md, the portraits section).

Each is an opponent with a workshop personality (src/services/bots/personality.py: sliders set the style, strength follows
target_elo) and his own opening book from his games in the archive and library (scripts/build_master_books.py →
books/<id>.json). Names, titles and mottos live on the client (bots.profiles.<id>); the mottos are our own wordings of the
style, not
quotations. Strength is refined by calibration (scripts/calibrate_bots.py).

The data is the MASTERS registry: a new master is a new entry, not a code change. The ready MASTER_BOTS bots go into the
bots/__init__.py registry (BOT_INSTANCES) and into the src/api/bots.py routes (MASTERS is read there too).
"""

from dataclasses import dataclass
from typing import ClassVar

import chess

from src.services.bots.base import BookEntry, HistoricalBot, load_bot_opening_book
from src.services.bots.personality import BotPersonalityConfig, PersonalityBot


@dataclass(frozen=True)
class Master:
    """
    A historical master of the second wave: id, name for PGN, years of life, strength, personality settings and the features by
    which
    his games are found in PGN.
    """
    id: str
    # Name for PGN: "Surname, Given name" in Latin letters.
    pgn_name: str
    # Years of life.
    era: str
    # Declared strength; matches target_elo in config.
    rating: int
    config: BotPersonalityConfig
    # How to find his games in PGN: part of the surname and exclusions (namesakes).
    surname: str
    exclude: tuple[str, ...] = ()


def _cfg(target_elo: int, **fields) -> BotPersonalityConfig:
    """Shorthand for the table: a personality with a given target_elo and the other slider fields."""
    return BotPersonalityConfig(target_elo=target_elo, **fields)


MASTERS: tuple[Master, ...] = (
    # Positional school: a fortified king, healthy structure, attack only when the position is ready.
    Master("steinitz", "Steinitz, William", "1836–1900", 2050,
           _cfg(2050, aggression=-40, king_safety=160, pawn_structure=180, center_control=140, randomness=15,
                draw_attitude=-20), "steinitz"),
    # A practical fighter: plays against the opponent, does not avoid complications.
    Master("lasker", "Lasker, Emanuel", "1868–1941", 2250,
           _cfg(2250, aggression=10, mobility=140, king_safety=120, randomness=25, draw_attitude=-50), "lasker",
           ("edward", "berthold")),
    # A rook endgame master: structure, passed pawns, patience.
    Master("rubinstein", "Rubinstein, Akiba", "1880–1961", 2200,
           _cfg(2200, aggression=-20, pawn_structure=170, center_control=130, passed_pawns=170, randomness=10),
           "rubinstein"),
    # Clarity and technique: simple positions, precise endgame, willingly simplifies.
    Master("capablanca", "Capablanca, Jose Raul", "1888–1942", 2300,
           _cfg(2300, aggression=-10, mobility=150, pawn_structure=150, passed_pawns=140, randomness=5,
                blunder_guard_cp=60, draw_attitude=30), "capablanca"),
    # Initiative and combinations: active pieces, centre, attack on the king.
    Master("alekhine", "Alekhine, Alexander", "1892–1946", 2300,
           _cfg(2300, aggression=80, mobility=170, center_control=150, king_safety=80, randomness=15,
                draw_attitude=-60), "alekhine"),
    # Third wave (16.11): masters from the 21.5 list and world champions of 1948-1969 (owner decision of 16.11). Games for
    # the books — the archive and the library (the "Masters' games" collection).
    # Piece play and attack: knights against bishops, a fight against dogma.
    Master("chigorin", "Chigorin, Mikhail", "1850–1908", 2150,
           _cfg(2150, aggression=60, mobility=160, king_safety=90, randomness=25, draw_attitude=-50), "chigorin", ()),
    # Classics: centre, mobile pieces, space.
    Master("tarrasch", "Tarrasch, Siegbert", "1862–1934", 2200,
           _cfg(2200, aggression=0, center_control=170, mobility=160, pawn_structure=120, randomness=10),
           "tarrasch", ()),
    # Attack on the king in the Queen's Gambit, sharp play.
    Master("pillsbury", "Pillsbury, Harry Nelson", "1872–1906", 2250,
           _cfg(2250, aggression=60, mobility=150, king_safety=90, randomness=15, draw_attitude=-40), "pillsbury", ()),
    # Gambits and traps: initiative at any cost.
    Master("marshall", "Marshall, Frank James", "1877–1944", 2200,
           _cfg(2200, aggression=90, mobility=150, king_safety=70, randomness=25, draw_attitude=-60), "marshall", ()),
    # Blockade, over-protection and control of the centre by pieces from afar.
    Master("nimzowitsch", "Nimzowitsch, Aron", "1886–1935", 2250,
           _cfg(2250, aggression=-30, pawn_structure=170, king_safety=140, center_control=110, randomness=15),
           "nimzowitsch", ()),
    # Hypermodern: flank openings and pressure on the centre.
    Master("reti", "Reti, Richard", "1889–1929", 2200,
           _cfg(2200, aggression=-10, center_control=130, mobility=140, randomness=15), "reti,", ()),
    # Unexpected openings and practical play.
    Master("tartakower", "Tartakower, Savielly", "1887–1956", 2150,
           _cfg(2150, aggression=20, mobility=130, randomness=30, draw_attitude=0), "tartakower", ()),
    # A deep plan, preparation and technique.
    Master("botvinnik", "Botvinnik, Mikhail", "1911–1995", 2400,
           _cfg(2400, aggression=10, pawn_structure=160, center_control=150, king_safety=130, randomness=5,
                blunder_guard_cp=60),
           "botvinnik", ()),
    # Sacrifices and attack: the position is on fire.
    Master("tal", "Tal, Mikhail", "1936–1992", 2450,
           _cfg(2450, aggression=100, mobility=180, king_safety=60, randomness=30, draw_attitude=-80), "tal,", ()),
    # Prophylaxis and safety: first take everything away from the opponent.
    Master("petrosian", "Petrosian, Tigran", "1929–1984", 2400,
           _cfg(2400, aggression=-60, king_safety=180, pawn_structure=160, randomness=5, blunder_guard_cp=80,
                draw_attitude=40),
           "petrosian", ("arshak",)),
)
# Lookup of a master by id (the bot key in the registry).
MASTERS_BY_ID = {m.id: m for m in MASTERS}


class MasterBot(PersonalityBot):
    """A master: style — personality sliders, opening — his own book (as with the historical bots of the first wave)."""

    # Set in the class created for a specific master (see MASTER_CLASSES).
    master: ClassVar[Master]

    def __init__(self, stockfish_path: str | None = None):
        """Bot from a master's settings: id, move source and book are its own, not "custom" from PersonalityBot."""
        super().__init__(self.master.config, stockfish_path)
        self.bot_id = self.master.id
        self.engine_source_name = f"{self.master.id}_style_engine"
        self.opening_book: dict[str, list[BookEntry]] = load_bot_opening_book(self.master.id)

    def _book_move(self, board: chess.Board) -> tuple[chess.Move, dict] | None:
        # Own book with the remark "... games in the archive", not the workshop's favourite openings.
        return HistoricalBot._book_move(self, board)


# A separate class for each master: the tournament simulation creates a fresh bot as type(bot)().
MASTER_CLASSES: dict[str, type[MasterBot]] = {
    m.id: type(f"{m.id.capitalize()}Bot", (MasterBot,), {"master": m}) for m in MASTERS
}
# Ready instances by id; the bots/__init__.py registry adds them to BOT_INSTANCES.
MASTER_BOTS: dict[str, MasterBot] = {key: cls() for key, cls in MASTER_CLASSES.items()}
