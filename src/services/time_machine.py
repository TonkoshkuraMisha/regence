# --- FILE: src/services/time_machine.py ---
"""
"Time Machine" (tasks 28.2-28.3): the player becomes a participant in a famous tournament of the past.

The tournament runs with the full historical field plus the player: in a round robin they play everyone, in a knockout they can
be eliminated. The masters' games among themselves are played by bots (simulation 15.2) - an alternative history results;
how the tournament really ended is kept by the registry (place and points of each), and the client shows it next to the
player's result.

The fields and results are checked against open sources (the crosstable of each tournament). Texts about the tournaments,
names and names are on the client (timeMachine.events.<key>, bots.guests.<id>): the server gives only keys and numbers. A
participant is either a historical master with a book and a portrait (bots/masters.py and the first-wave bots), or a master
of the past from bots/guests.py.

The "Time Machine" has its own slot next to the player's ordinary tournament: one running historical tournament does not
interfere with the career and the player's own tournaments.

Data: the _EVENTS registry in this file (fields and results are constants); the player's history is the tournaments table
(event_key) and tournament_players. The participants' strength comes from calibration (bots/calibration.py) or the stated
rating of the master of the past. Called by src/api/tournaments.py and src/api/bots.py; the tournament is created by
tournaments.create_tournament.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DomainError
from src.models.tournament import Tournament, TournamentPlayer
from src.models.user import User
from src.services import tournament_rules as rules
from src.services import tournaments as tournaments_service
from src.services.bots.calibration import strength_of
from src.services.bots.guests import GUESTS_BY_ID


@dataclass(frozen=True)
class Entry:
    """A participant and their real result: place (None - eliminated without a place), points (None - in a knockout)."""

    id: str
    place: int | None
    score: float | None = None


@dataclass(frozen=True)
class Event:
    """
    A "Time Machine" tournament: key, year, format, number of rounds and the historical field with real places and points.
    """
    key: str
    year: int
    format: tournaments_service.Format
    field: tuple[Entry, ...]
    cycles: int = 1
    # The real table is incomplete: the tournament was not finished (Mannheim 1914 was interrupted by the war) or draws
    # gave no points - the sum of points is less than the number of games. The player's tournament runs to the end.
    partial: bool = False

    @property
    def size(self) -> int:
        """Participants including the player."""
        return len(self.field) + 1

    @property
    def player_games(self) -> int | None:
        """How many games the player plays in a round robin; in a knockout it depends on the player."""
        return (self.size - 1) * self.cycles if self.format == "round_robin" else None

    @property
    def rounds(self) -> int:
        """Number of rounds (grid circuits) of the tournament including the player."""
        if self.format == "round_robin":
            return len(rules.round_robin_schedule(self.size, self.cycles))
        return rules.bracket_size(self.size).bit_length() - 1


def _table(*rows: tuple[str, float]) -> tuple[Entry, ...]:
    """Final table of a round robin: participants by place, a tie - one place for all who scored the same."""
    entries, place = [], 0
    for index, (player, score) in enumerate(rows):
        if index == 0 or score != rows[index - 1][1]:
            place = index + 1
        entries.append(Entry(player, place, score))
    return tuple(entries)


_EVENTS: tuple[Event, ...] = (
    # The first international tournament: sixteen participants, knockout matches. Anderssen won.
    Event("london_1851", 1851, "knockout", (
        Entry("anderssen", 1), Entry("wyvill", 2), Entry("williams", 3), Entry("staunton", 4),
        Entry("szen", 5), Entry("kennedy_h", 6), Entry("horwitz", 7), Entry("mucklow", 8),
        # Eliminated in the first round.
        Entry("kieseritzky", None), Entry("newham", None), Entry("bird", None), Entry("brodie", None),
        Entry("lowe", None), Entry("mayet", None), Entry("lowenthal", None), Entry("kennedy_e", None),
    )),
    # The strongest tournament of the 19th century: twenty-two participants in one round. 22-year-old Pillsbury won.
    Event("hastings_1895", 1895, "round_robin", _table(
        ("pillsbury", 16.5), ("chigorin", 16), ("lasker", 15.5), ("tarrasch", 14), ("steinitz", 13),
        ("schiffers", 12), ("bardeleben", 11.5), ("teichmann", 11.5), ("schlechter", 11), ("blackburne", 10.5),
        ("walbrodt", 10), ("janowski", 9.5), ("mason", 9.5), ("burn", 9.5), ("gunsberg", 9), ("bird", 9),
        ("albin", 8.5), ("marco", 8.5), ("pollock", 8), ("mieses", 7.5), ("tinsley", 7.5), ("vergani", 3),
    )),
    # A preliminary tournament of eleven in one round; the top five then played a final, which Lasker won.
    Event("st_petersburg_1914", 1914, "round_robin", _table(
        ("capablanca", 8), ("lasker", 6.5), ("tarrasch", 6.5), ("alekhine", 6), ("marshall", 6),
        ("bernstein", 5), ("rubinstein", 5), ("nimzowitsch", 4), ("blackburne", 3.5), ("janowski", 3.5),
        ("gunsberg", 1),
    )),
    # Eleven participants in two rounds. Lasker won, ahead of Capablanca and Alekhine.
    Event("new_york_1924", 1924, "round_robin", _table(
        ("lasker", 16), ("capablanca", 14.5), ("alekhine", 12), ("marshall", 11), ("reti", 10.5), ("maroczy", 10),
        ("bogoljubow", 9.5), ("tartakower", 8), ("yates", 7), ("lasker_edward", 6.5), ("janowski", 5),
    ), cycles=2),
    # The eight strongest in the world in two rounds. First place was shared by Keres and Fine.
    Event("avro_1938", 1938, "round_robin", _table(
        ("keres", 8.5), ("fine", 8.5), ("botvinnik", 7.5), ("euwe", 7), ("reshevsky", 7), ("alekhine", 7),
        ("capablanca", 6), ("flohr", 4.5),
    ), cycles=2),
    # Nine participants in two rounds (the tenth, Stern, dropped out after four rounds, his games are not counted).
    # Anderssen won.
    Event("baden_baden_1870", 1870, "round_robin", _table(
        ("anderssen", 11), ("steinitz", 10.5), ("neumann", 10), ("blackburne", 10), ("paulsen", 7.5),
        ("de_vere", 6.5), ("winawer", 6.5), ("rosenthal", 5), ("minckwitz", 5),
    ), cycles=2),
    # Fourteen participants in two rounds (in the original draws were replayed). Zukertort won, three points
    # ahead of Steinitz.
    Event("london_1883", 1883, "round_robin", _table(
        ("zukertort", 22), ("steinitz", 19), ("blackburne", 16.5), ("chigorin", 16), ("mackenzie", 15.5),
        ("englisch", 15.5), ("mason", 15.5), ("rosenthal", 14), ("winawer", 13), ("bird", 12), ("noa", 9.5),
        ("sellman", 6.5), ("mortimer", 3), ("skipworth", 3),
    ), cycles=2),
    # The four strongest in six rounds. Lasker won.
    Event("st_petersburg_1895", 1895, "round_robin", _table(
        ("lasker", 11.5), ("steinitz", 9.5), ("pillsbury", 8), ("chigorin", 7),
    ), cycles=6),
    # Fifteen participants in one round. Capablanca won - in his first big European tournament.
    Event("san_sebastian_1911", 1911, "round_robin", _table(
        ("capablanca", 9.5), ("rubinstein", 9), ("vidmar", 9), ("marshall", 8.5), ("tarrasch", 7.5),
        ("schlechter", 7.5), ("nimzowitsch", 7.5), ("bernstein", 7), ("spielmann", 7), ("teichmann", 6.5),
        ("maroczy", 6), ("janowski", 6), ("burn", 5), ("duras", 5), ("leonhardt", 4),
    )),
    # Six in four rounds. Capablanca won without losing a single game.
    Event("new_york_1927", 1927, "round_robin", _table(
        ("capablanca", 14), ("alekhine", 11.5), ("nimzowitsch", 10.5), ("vidmar", 10), ("spielmann", 8),
        ("marshall", 6),
    ), cycles=4),
    # Fifteen participants in one round. First place was shared by Botvinnik and Capablanca.
    Event("nottingham_1936", 1936, "round_robin", _table(
        ("botvinnik", 10), ("capablanca", 10), ("euwe", 9.5), ("fine", 9.5), ("reshevsky", 9.5), ("alekhine", 9),
        ("flohr", 8.5), ("lasker", 8.5), ("vidmar", 6), ("bogoljubow", 5.5), ("tartakower", 5.5), ("tylor", 4.5),
        ("alexander", 3.5), ("thomas", 3), ("winter", 2.5),
    )),
    # Eighteen participants in two rounds. First place was shared by Steinitz and Winawer.
    Event("vienna_1882", 1882, "round_robin", _table(
        ("steinitz", 24), ("winawer", 24), ("mason", 23), ("zukertort", 22.5), ("mackenzie", 22.5),
        ("blackburne", 21.5), ("englisch", 19.5), ("paulsen", 18.5), ("wittek", 18), ("weiss", 16.5), ("hruby", 16),
        ("chigorin", 14), ("schwarz", 14), ("meitner", 13), ("bird", 12), ("ware", 11), ("noa", 9), ("fleissig", 7),
    ), cycles=2),
    # Nineteen participants in one round. Lasker won.
    Event("nuremberg_1896", 1896, "round_robin", _table(
        ("lasker", 13.5), ("maroczy", 12.5), ("tarrasch", 12), ("pillsbury", 12), ("janowski", 11.5),
        ("steinitz", 11), ("walbrodt", 10.5), ("schlechter", 10.5), ("schiffers", 9.5), ("chigorin", 9.5),
        ("blackburne", 9), ("charousek", 8.5), ("marco", 8), ("albin", 7), ("winawer", 6.5), ("showalter", 5.5),
        ("porges", 5.5), ("schallopp", 4.5), ("teichmann", 4),
    )),
    # Fifteen participants in two rounds; Teichmann dropped out after four rounds (in the table - last, with the two
    # points he had scored). Lasker won.
    Event("london_1899", 1899, "round_robin", _table(
        ("lasker", 23.5), ("maroczy", 19), ("pillsbury", 19), ("janowski", 19), ("schlechter", 18),
        ("blackburne", 16.5), ("chigorin", 16), ("showalter", 13.5), ("mason", 13), ("steinitz", 12.5),
        ("cohn", 12.5), ("lee", 10.5), ("bird", 8), ("tinsley", 7), ("teichmann", 2),
    ), cycles=2),
    # Fourteen participants in two rounds. Tarrasch won; Colonel Moreau lost all 26 games.
    Event("monte_carlo_1903", 1903, "round_robin", _table(
        ("tarrasch", 20), ("maroczy", 19), ("pillsbury", 18.5), ("schlechter", 17), ("teichmann", 16.5),
        ("marco", 15.5), ("wolf", 14), ("mieses", 13), ("marshall", 12), ("taubenhaus", 10.5), ("mason", 10.5),
        ("albin", 8), ("reggio", 7.5), ("moreau", 0),
    ), cycles=2),
    # Twenty-one participants in one round. Rubinstein won; Chigorin's last tournament.
    Event("carlsbad_1907", 1907, "round_robin", _table(
        ("rubinstein", 15), ("maroczy", 14.5), ("leonhardt", 13.5), ("nimzowitsch", 12.5), ("schlechter", 12.5),
        ("vidmar", 12), ("teichmann", 11.5), ("duras", 11.5), ("salwe", 11), ("wolf", 10.5), ("marshall", 10),
        ("dus_chotimirsky", 10), ("spielmann", 9.5), ("tartakower", 9), ("janowski", 8.5), ("berger", 7.5),
        ("chigorin", 7.5), ("mieses", 7.5), ("olland", 6.5), ("cohn_erich", 5), ("johner_paul", 4.5),
    )),
    # Twenty-one participants in one round. Bogoljubov won, ahead of Lasker and Capablanca.
    Event("moscow_1925", 1925, "round_robin", _table(
        ("bogoljubow", 15.5), ("lasker", 14), ("capablanca", 13.5), ("marshall", 12.5), ("tartakower", 12),
        ("torre", 12), ("reti", 11.5), ("romanovsky", 11.5), ("grunfeld", 10.5), ("ilyin_zhenevsky", 10.5),
        ("bohatyrchuk", 10), ("verlinsky", 9.5), ("spielmann", 9.5), ("rubinstein", 9.5), ("levenfish", 9),
        ("rabinovich", 8.5), ("yates", 7), ("samisch", 6.5), ("gotthilf", 6.5), ("dus_chotimirsky", 6),
        ("zubarev", 4.5),
    )),
    # Twenty-two participants in one round. Nimzowitsch won - the greatest success of his career.
    Event("carlsbad_1929", 1929, "round_robin", _table(
        ("nimzowitsch", 15), ("capablanca", 14.5), ("spielmann", 14.5), ("rubinstein", 13.5), ("becker", 12),
        ("vidmar", 12), ("euwe", 12), ("bogoljubow", 11.5), ("grunfeld", 11), ("canal", 10.5), ("mattison", 10.5),
        ("tartakower", 10), ("maroczy", 10), ("colle", 10), ("treybal", 10), ("samisch", 9.5), ("yates", 9.5),
        ("johner_paul", 9), ("marshall", 9), ("gilg", 8), ("thomas", 6), ("menchik", 3),
    )),
    # Fourteen participants in two rounds. Alekhine did not lose a single game and finished 5.5 points ahead of the runner-up.
    Event("bled_1931", 1931, "round_robin", _table(
        ("alekhine", 20.5), ("bogoljubow", 15), ("nimzowitsch", 14), ("kashdan", 13.5), ("vidmar", 13.5),
        ("flohr", 13.5), ("stoltz", 13.5), ("tartakower", 13), ("spielmann", 12.5), ("kostic", 12.5), ("maroczy", 12),
        ("colle", 10.5), ("asztalos", 9.5), ("pirc", 8.5),
    ), cycles=2),
    # The first American chess congress: sixteen participants, knockout matches. Morphy won.
    Event("new_york_1857", 1857, "knockout", (
        Entry("morphy", 1), Entry("paulsen", 2), Entry("lichtenhein", 3), Entry("raphael", 4), Entry("meek", None),
        Entry("perrin", None), Entry("montgomery", None), Entry("marache", None), Entry("thompson", None),
        Entry("fuller", None), Entry("stanley", None), Entry("knott", None), Entry("calthrop", None),
        Entry("allison", None), Entry("kennicott", None), Entry("fiske", None),
    )),
    # Twelve participants in two rounds. Winawer and Zukertort shared first place; the play-off match was won by
    # Zukertort.
    Event("paris_1878", 1878, "round_robin", _table(
        ("winawer", 16.5), ("zukertort", 16.5), ("blackburne", 14.5), ("mackenzie", 13), ("bird", 13),
        ("anderssen", 12.5), ("englisch", 11.5), ("rosenthal", 11.5), ("clerc", 8.5), ("mason", 8.5),
        ("gifford", 3.5), ("pitschel", 2.5),
    ), cycles=2),
    # Seventeen participants in one round (in the original one draw was replayed once). Lasker won.
    Event("paris_1900", 1900, "round_robin", _table(
        ("lasker", 14.5), ("pillsbury", 12.5), ("marshall", 12), ("maroczy", 12), ("burn", 11), ("chigorin", 10.5),
        ("schlechter", 10), ("marco", 10), ("mieses", 10), ("showalter", 9), ("janowski", 9), ("mason", 4.5),
        ("brody", 4), ("rosen", 3), ("mortimer", 2), ("sterling", 1), ("didier", 1),
    )),
    # The Chigorin Memorial: nineteen participants in one round. First place was shared by Rubinstein and Lasker.
    Event("st_petersburg_1909", 1909, "round_robin", _table(
        ("rubinstein", 14.5), ("lasker", 14.5), ("spielmann", 11), ("duras", 11), ("bernstein", 10.5),
        ("teichmann", 10), ("perlis", 9.5), ("cohn_erich", 9), ("schlechter", 9), ("salwe", 9), ("tartakower", 8.5),
        ("mieses", 8.5), ("dus_chotimirsky", 8), ("forgacs", 7.5), ("burn", 7), ("vidmar", 7), ("speijer", 6),
        ("freymann", 5.5), ("znosko_borovsky", 5),
    )),
    # Twelve leading masters in one round. Bogoljubov won, ahead of Capablanca.
    Event("bad_kissingen_1928", 1928, "round_robin", _table(
        ("bogoljubow", 8), ("capablanca", 7), ("euwe", 6.5), ("rubinstein", 6.5), ("nimzowitsch", 6), ("reti", 5.5),
        ("tartakower", 5), ("marshall", 5), ("yates", 5), ("spielmann", 4.5), ("tarrasch", 4), ("mieses", 3),
    )),
    # Nineteen participants in two rounds (the withdrawn Schwarz is not in the table). First place - Tarrasch and Pillsbury.
    Event("vienna_1898", 1898, "round_robin", _table(
        ("tarrasch", 27.5), ("pillsbury", 27.5), ("janowski", 25.5), ("steinitz", 23.5), ("schlechter", 21.5),
        ("chigorin", 20), ("burn", 20), ("lipke", 19.5), ("maroczy", 19.5), ("alapin", 18), ("blackburne", 17),
        ("schiffers", 17), ("marco", 16.5), ("showalter", 15), ("walbrodt", 14.5), ("halprin", 14), ("caro", 12.5),
        ("baird", 8), ("trenchard", 5),
    ), cycles=2),
    # Twenty-six participants in one round. Teichmann won. Vidmar has 15: the published table has a misprint (15.5).
    Event("carlsbad_1911", 1911, "round_robin", _table(
        ("teichmann", 18), ("rubinstein", 17), ("schlechter", 17), ("rotlewi", 16), ("marshall", 15.5),
        ("nimzowitsch", 15.5), ("vidmar", 15), ("leonhardt", 13.5), ("tartakower", 13.5), ("duras", 13.5),
        ("alekhine", 13.5), ("spielmann", 13), ("perlis", 12), ("cohn_erich", 11.5), ("levenfish", 11.5),
        ("suchting", 11.5), ("burn", 11), ("salwe", 11), ("johner_paul", 10.5), ("rabinovich_abram", 10.5),
        ("kostic", 10.5), ("dus_chotimirsky", 10), ("alapin", 8.5), ("chajes", 8.5), ("fahrni", 8.5), ("jaffe", 8.5),
    )),
    # The tournament was interrupted by the war after 11 rounds of 17: the real table is as of the stop. The first prize
    # went to Alekhine.
    Event("mannheim_1914", 1914, "round_robin", _table(
        ("alekhine", 9.5), ("vidmar", 8.5), ("spielmann", 8), ("breyer", 7), ("marshall", 7), ("reti", 7),
        ("janowski", 6.5), ("bogoljubow", 5.5), ("tarrasch", 5.5), ("duras", 5), ("john", 5), ("tartakower", 4.5),
        ("fahrni", 4), ("post", 4), ("carls", 3.5), ("kruger", 3.5), ("flamberg", 3), ("mieses", 2),
    ), partial=True),
    # Eighteen participants in one round. First place was shared by Alekhine, Bogoljubov and Maroczy.
    Event("carlsbad_1923", 1923, "round_robin", _table(
        ("alekhine", 11.5), ("bogoljubow", 11.5), ("maroczy", 11.5), ("reti", 10.5), ("grunfeld", 10.5),
        ("nimzowitsch", 10), ("treybal", 10), ("yates", 9.5), ("teichmann", 9), ("tartakower", 8.5), ("tarrasch", 8),
        ("rubinstein", 7.5), ("bernstein_jacob", 7), ("wolf", 6.5), ("samisch", 6), ("thomas", 5.5), ("spielmann", 5),
        ("chajes", 5),
    )),
    # Fourteen participants in one round; draws were replayed - in the real table only wins. Anderssen won.
    Event("london_1862", 1862, "round_robin", _table(
        ("anderssen", 11), ("paulsen", 9), ("owen", 7), ("macdonnell", 7), ("dubois", 6), ("steinitz", 6),
        ("barnes", 6), ("hannah", 4), ("blackburne", 3), ("lowenthal", 3), ("robey", 2), ("deacon", 2),
        ("mongredien", 2), ("green", 2),
    ), partial=True),
    # Thirteen participants in two rounds; a draw gave points to nobody - in the real table only wins.
    # Kolisch won.
    Event("paris_1867", 1867, "round_robin", _table(
        ("kolisch", 20), ("winawer", 19), ("steinitz", 18), ("neumann", 17), ("de_vere", 14), ("riviere", 11),
        ("golmayo", 10), ("czarnowski", 9), ("rosenthal", 6), ("loyd", 6), ("dandre", 6), ("from", 5),
        ("rousseau", 5),
    ), cycles=2, partial=True),
    # The second congress of the German Chess Federation: seventeen participants in one round (Pitschel dropped out after three
    # games, they are not counted). Blackburne won.
    Event("berlin_1881", 1881, "round_robin", _table(
        ("blackburne", 14), ("zukertort", 11), ("winawer", 10.5), ("chigorin", 10.5), ("mason", 9.5), ("wittek", 9.5),
        ("minckwitz", 8.5), ("schwarz_jacques", 8.5), ("berger", 8), ("paulsen", 8), ("paulsen_w", 7.5),
        ("schallopp", 7), ("riemann", 6.5), ("wemmers", 6.5), ("noa", 5.5), ("schmid", 3.5), ("schutz", 1.5),
    )),
    # Sixteen participants in one round: eight Europeans and eight Americans. Marshall won without losses;
    # the Cambridge Springs Defence is named after the tournament.
    Event("cambridge_springs_1904", 1904, "round_robin", _table(
        ("marshall", 13), ("janowski", 11), ("lasker", 11), ("marco", 9), ("showalter", 8.5), ("schlechter", 7.5),
        ("chigorin", 7.5), ("mieses", 7), ("pillsbury", 7), ("fox", 6.5), ("teichmann", 6.5), ("lawrence", 5.5),
        ("napier", 5.5), ("barry", 5), ("hodges", 5), ("delmar", 4.5),
    )),
    # The last of the Monte Carlo tournaments of 1901-1904: six participants in two rounds. Maroczy won.
    Event("monte_carlo_1904", 1904, "round_robin", _table(
        ("maroczy", 7.5), ("schlechter", 7), ("marshall", 6.5), ("gunsberg", 4), ("marco", 3), ("swiderski", 2),
    ), cycles=2),
    # The championship tournament in Ostend: six winners of international tournaments in four rounds. Tarrasch won.
    Event("ostend_1907", 1907, "round_robin", _table(
        ("tarrasch", 12.5), ("schlechter", 12), ("janowski", 11.5), ("marshall", 11.5), ("burn", 8),
        ("chigorin", 4.5),
    ), cycles=4),
    # The first international tournament in Prague: twenty participants in one round. First place was shared by Duras and
    # Schlechter.
    Event("prague_1908", 1908, "round_robin", _table(
        ("duras", 13.5), ("schlechter", 13.5), ("vidmar", 13), ("rubinstein", 12.5), ("teichmann", 12),
        ("maroczy", 11.5), ("leonhardt", 11), ("marshall", 11), ("salwe", 11), ("janowski", 10.5),
        ("dus_chotimirsky", 9.5), ("alapin", 9), ("suchting", 8.5), ("mieses", 8.5), ("spielmann", 7.5),
        ("prokes", 6.5), ("bardeleben", 6), ("kvicala", 5.5), ("rabinovich_abram", 5), ("treybal_frantisek", 4.5),
    )),
    # Twenty participants in one round. First place was shared by Maroczy, Schlechter and Duras; 18-year-old Reti took
    # last place.
    Event("vienna_1908", 1908, "round_robin", _table(
        ("maroczy", 14), ("schlechter", 14), ("duras", 14), ("rubinstein", 13), ("teichmann", 12),
        ("spielmann", 11.5), ("perlis", 11), ("tartakower", 11), ("leonhardt", 10), ("mieses", 10), ("marshall", 10),
        ("swiderski", 9.5), ("salwe", 8.5), ("johner_paul", 7.5), ("berger", 7), ("suchting", 6.5),
        ("bardeleben", 6.5), ("alapin", 6.5), ("cohn_erich", 6), ("reti", 1.5),
    )),
    # The seventeenth congress of the German Chess Federation: seventeen participants in one round (Jacob dropped out after
    # six rounds, his games are not counted). Schlechter won.
    Event("hamburg_1910", 1910, "round_robin", _table(
        ("schlechter", 11.5), ("duras", 11), ("nimzowitsch", 10.5), ("spielmann", 10), ("teichmann", 9.5),
        ("marshall", 9.5), ("dus_chotimirsky", 8.5), ("alekhine", 8.5), ("tarrasch", 8), ("forgacs", 8),
        ("leonhardt", 7), ("tartakower", 7), ("salwe", 7), ("kohnlein", 7), ("speijer", 5.5), ("john", 5),
        ("yates", 2.5),
    )),
    # Eleven participants in two rounds; Forgacs played only the first round, his other ten games are not counted in the
    # real table. Rubinstein won.
    Event("san_sebastian_1912", 1912, "round_robin", _table(
        ("rubinstein", 12.5), ("nimzowitsch", 12), ("spielmann", 12), ("tarrasch", 11.5), ("perlis", 10),
        ("marshall", 9.5), ("duras", 8.5), ("schlechter", 8), ("teichmann", 8), ("leonhardt", 5), ("forgacs", 3),
    ), cycles=2, partial=True),
    # Fourteen participants in one round. Lasker won without losses, one point ahead of Reti.
    Event("moravska_ostrava_1923", 1923, "round_robin", _table(
        ("lasker", 10.5), ("reti", 9.5), ("grunfeld", 8.5), ("selezniev", 7.5), ("tartakower", 7), ("euwe", 7),
        ("tarrasch", 6.5), ("bogoljubow", 6.5), ("spielmann", 6), ("rubinstein", 5.5), ("pokorny", 5),
        ("hromadka", 4.5), ("wolf", 4.5), ("walter", 2.5),
    )),
    # Nineteen participants in one round (the twentieth, Bardeleben, dropped out after the first game). Haruzek won,
    # half a point ahead of Walbrodt.
    Event("berlin_1897", 1897, "round_robin", _table(
        ("charousek", 13.5), ("walbrodt", 13), ("blackburne", 12), ("janowski", 11.5), ("burn", 11),
        ("schlechter", 10.5), ("marco", 10.5), ("alapin", 10.5), ("caro", 10), ("chigorin", 9.5), ("schiffers", 9),
        ("metger", 8.5), ("cohn", 7.5), ("winawer", 7.5), ("suchting", 7), ("teichmann", 6.5), ("englisch", 5.5),
        ("zinkl", 5.5), ("albin", 2),
    )),
    # Sixteen participants in one round. Alekhine scored 14 out of 15 and finished three and a half points ahead of the
    # runner-up.
    Event("san_remo_1930", 1930, "round_robin", _table(
        ("alekhine", 14), ("nimzowitsch", 10.5), ("rubinstein", 10), ("bogoljubow", 9.5), ("yates", 9),
        ("ahues", 8.5), ("spielmann", 8), ("vidmar", 8), ("maroczy", 7.5), ("tartakower", 7.5), ("colle", 6.5),
        ("kmoch", 6.5), ("araiza", 4.5), ("monticelli", 4), ("grau", 3.5), ("romih", 2.5),
    )),
    # The sixth American chess congress: twenty participants in two rounds - one of the longest tournaments in
    # history. Chigorin and Weiss shared first place.
    Event("new_york_1889", 1889, "round_robin", _table(
        ("chigorin", 29), ("weiss", 29), ("gunsberg", 28.5), ("blackburne", 27), ("burn", 26), ("lipschutz", 25.5),
        ("mason", 22), ("judd", 20), ("delmar", 18), ("showalter", 18), ("pollock", 17.5), ("bird", 17),
        ("taubenhaus", 17), ("baird", 16), ("burille", 15), ("hanham", 14), ("gossip", 13.5), ("martinez", 13.5),
        ("baird_john", 7), ("macleod", 6.5),
    ), cycles=2),
    # The third All-Russian masters' tournament in Kyiv: nineteen participants in one round (the unplayed games
    # of the withdrawn Breyev are credited to his opponents). Chigorin won.
    Event("kyiv_1903", 1903, "round_robin", _table(
        ("chigorin", 15), ("bernstein", 14), ("yurevich", 13.5), ("salwe", 13), ("rubinstein", 11.5),
        ("znosko_borovsky", 11), ("lowtzky", 11), ("levitsky", 10.5), ("izbinsky", 9.5), ("lebedev", 9.5),
        ("rabinovich_abram", 8.5), ("schiffers", 8.5), ("kulomzin", 8), ("kalinsky", 7.5), ("dus_chotimirsky", 7),
        ("benko", 6.5), ("nikolaev", 4.5), ("stamm", 2), ("breev", 0),
    )),
    # A final of the five winners of the preliminary tournament in two rounds. In the original the preliminary tournament's
    # points counted; here - only the final's points. Lasker won.
    Event("st_petersburg_1914_final", 1914, "round_robin", _table(
        ("lasker", 7), ("capablanca", 5), ("alekhine", 4), ("tarrasch", 2), ("marshall", 2),
    ), cycles=2),
    # Sixteen participants in one round: Capablanca's first tournament as world champion. He won without losses.
    Event("london_1922", 1922, "round_robin", _table(
        ("capablanca", 13), ("alekhine", 11.5), ("vidmar", 11), ("rubinstein", 10.5), ("bogoljubow", 9),
        ("reti", 8.5), ("tartakower", 8.5), ("maroczy", 8), ("yates", 8), ("atkins", 6), ("euwe", 5.5),
        ("wahltuch", 5), ("znosko_borovsky", 5), ("watson", 4.5), ("morrison", 4.5), ("marotti", 1.5),
    )),
    # Twenty-one participants in one round - the strongest players in the world except Capablanca and Lasker. Alekhine
    # won without losses.
    Event("baden_baden_1925", 1925, "round_robin", _table(
        ("alekhine", 16), ("rubinstein", 14.5), ("samisch", 13.5), ("bogoljubow", 13), ("marshall", 12.5),
        ("tartakower", 12.5), ("rabinovich", 12), ("grunfeld", 11.5), ("nimzowitsch", 11), ("torre", 10.5),
        ("reti", 10), ("treybal", 10), ("spielmann", 10), ("carls", 9), ("yates", 8), ("rosselli", 7.5),
        ("tarrasch", 7.5), ("colle", 7), ("mieses", 6.5), ("thomas", 6), ("kolste", 1.5),
    )),
    # Eighteen participants in one round. Spielmann finished half a point ahead of Alekhine.
    Event("semmering_1926", 1926, "round_robin", _table(
        ("spielmann", 13), ("alekhine", 12.5), ("vidmar", 12), ("nimzowitsch", 11.5), ("tartakower", 11.5),
        ("rubinstein", 10), ("tarrasch", 10), ("reti", 9.5), ("grunfeld", 9), ("janowski", 8.5), ("treybal", 8),
        ("vajda", 7.5), ("yates", 7), ("gilg", 6), ("kmoch", 6), ("davidson", 5.5), ("michel", 4.5), ("rosselli", 1),
    )),
    # The first big international tournament after the First World War: fourteen participants of the main tournament in
    # one round. Reti won.
    Event("goteborg_1920", 1920, "round_robin", _table(
        ("reti", 9.5), ("rubinstein", 9), ("bogoljubow", 8), ("kostic", 7.5), ("mieses", 7.5), ("tarrasch", 7.5),
        ("tartakower", 7.5), ("maroczy", 6), ("breyer", 5.5), ("marco", 5.5), ("spielmann", 5), ("nimzowitsch", 4.5),
        ("moller", 4), ("selezniev", 4),
    )),
    # Fifteen participants in one round. Rubinstein won without losses; Spielmann did not finish because of illness (in
    # the last two games he is credited with losses).
    Event("vienna_1922", 1922, "round_robin", _table(
        ("rubinstein", 11.5), ("tartakower", 10), ("wolf", 9.5), ("alekhine", 9), ("maroczy", 9), ("tarrasch", 9),
        ("grunfeld", 8), ("reti", 7.5), ("bogoljubow", 6.5), ("vukovic", 6), ("spielmann", 6), ("samisch", 5.5),
        ("takacs", 4), ("konig", 2), ("kmoch", 1.5),
    )),
    # Six participants in two rounds. Nimzowitsch won without losses; the "immortal zugzwang game" was played here,
    # Samisch - Nimzowitsch.
    Event("copenhagen_1923", 1923, "round_robin", _table(
        ("nimzowitsch", 8), ("samisch", 6), ("tartakower", 6), ("spielmann", 5.5), ("jacobsen", 3), ("moller", 1.5),
    ), cycles=2),
)
# The feed is by year; tournaments of the same year - by key.
EVENTS: tuple[Event, ...] = tuple(sorted(_EVENTS, key=lambda event: (event.year, event.key)))
EVENTS_BY_KEY = {event.key: event for event in EVENTS}


def participant(player_id: str) -> tuple[tournaments_service.ParticipantSpec, int]:
    """A tournament participant by registry id: (who they will be in the tournament, strength)."""
    from src.api.bots import BOT_METADATA

    guest = GUESTS_BY_ID.get(player_id)
    if guest is not None:
        return tournaments_service.ParticipantSpec("guest", guest.id), guest.rating
    meta = BOT_METADATA.get(player_id)
    if meta is None:
        raise KeyError(player_id)
    return tournaments_service.ParticipantSpec("bot", player_id), strength_of(player_id, int(str(meta["rating"]))).rating


async def _history(db: AsyncSession, user_id: int) -> dict[str, dict]:
    """For each tournament: the one running (id) and the player's best place in the finished ones."""
    rows = (await db.execute(
        select(Tournament.id, Tournament.event_key, Tournament.status, Tournament.withdrawn_at, TournamentPlayer.place)
        .join(TournamentPlayer, (TournamentPlayer.tournament_id == Tournament.id) & (TournamentPlayer.user_id == user_id))
        .where(Tournament.owner_id == user_id, Tournament.event_key.is_not(None))
        .order_by(Tournament.id)
    )).all()
    history: dict[str, dict] = {}
    for tournament_id, key, status, withdrawn_at, place in rows:
        item = history.setdefault(key, {"active_id": None, "best_place": None, "played": 0})
        if status == "active" and withdrawn_at is None:
            item["active_id"] = tournament_id
        elif status == "finished" and place is not None:
            item["played"] += 1
            item["best_place"] = place if item["best_place"] is None else min(item["best_place"], place)
    return history


async def overview(db: AsyncSession, user_id: int | None) -> list[dict]:
    """
    The feed of tournaments by year: the field with strength and the real result. For a player who has joined - also what
    they have already played; for a guest (user_id = None) the feed is shown without history: tournaments of the past are
    content, not personal data.
    """
    history = await _history(db, user_id) if user_id is not None else {}
    result = []
    for event in EVENTS:
        field = []
        for entry in event.field:
            spec, rating = participant(entry.id)
            field.append({"id": entry.id, "kind": spec.kind, "rating": rating, "place": entry.place, "score": entry.score})
        mine = history.get(event.key, {})
        result.append({
            "key": event.key, "year": event.year, "format": event.format, "cycles": event.cycles, "size": event.size,
            "rounds": event.rounds, "player_games": event.player_games, "partial": event.partial, "field": field,
            "active_id": mine.get("active_id"), "best_place": mine.get("best_place"), "played": mine.get("played", 0),
        })
    return result


async def start(db: AsyncSession, user: User, key: str, base_time_ms: int, increment_ms: int) -> Tournament:
    """Creates a player's tournament from a historical event: the whole historical field plus the player."""
    event = EVENTS_BY_KEY.get(key)
    if event is None:
        raise DomainError("time_machine_event_unknown", event=key)
    participants = [participant(entry.id)[0] for entry in event.field]
    return await tournaments_service.create_tournament(
        db, user, event.format, event.size, participants, base_time_ms, increment_ms,
        cycles=event.cycles, open_size=True, event_key=event.key,
    )
