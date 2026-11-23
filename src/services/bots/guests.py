# --- FILE: src/services/bots/guests.py ---
"""
Masters of the past — participants of famous tournaments ("Time Machine", task 28.2).

The player needs the full historical field, not only the best-known names: in London 1851 sixteen people played,
in Hastings 1895 — twenty-two. Each participant here is an opponent with a workshop personality
(BotPersonalityConfig): the style follows the known manner of play, the strength follows historical estimates relative to the
already
calibrated masters (bots/masters.py: Staunton 2000, Anderssen 2100, Lasker 2250, Capablanca 2300). In a tournament the
participant is stored as a persona with the key "guest:<id>": the simulation and the player's game work as with any
workshop opponent, and the name in the player's language is taken by the client (bots.guests.<id>). Whoever became associated
with their own
opening in history plays it (SIGNATURE_OPENINGS): Vinawer — the Vinawer variation, Grunfeld — the Grunfeld Defence, Bird —
Bird's Opening.

The data is the GUESTS registry (a new master is a new entry). It is read by time_machine.py and tournaments.py (the field of
the tournaments,
simulation) and src/api/bots.py (the opponent in a game).

All are deceased chess players (rule 1). Years of life were checked against open sources (17.11); where there are no reliable
dates, none are given. There are no portraits or own opening books for the masters of the past yet: that is the next step.
"""

from dataclasses import dataclass

from src.services import openings
from src.services.bots.personality import BotPersonalityConfig

# Prefix of a master-of-the-past key in a tournament field and in games.personality_name.
GUEST_PREFIX = "guest:"


@dataclass(frozen=True)
class Guest:
    """
    A master of the past is a participant of the "Time Machine": id, name for PGN, years of life (only reliable ones), strength
    and personality
    settings. key is the key under which he is stored in a tournament.
    """
    id: str
    # Latin name for PGN and the archive: "Surname, Given name".
    pgn_name: str
    # Years of life — only those checked against sources; None — no reliable dates could be found (three little-known
    # participants of London 1851).
    era: str | None
    rating: int
    config: BotPersonalityConfig

    @property
    def key(self) -> str:
        """The master's key in a tournament and in the database: "guest:<id>"."""
        return f"{GUEST_PREFIX}{self.id}"


# Opening names repeated in SIGNATURE_OPENINGS (as in the open openings table).
QGD = "Queen's Gambit Declined"
RUY_LOPEZ = "Ruy Lopez"
KINGS_GAMBIT = "King's Gambit Accepted"
VIENNA = "Vienna Game"
FRENCH = "French Defense"

# Signature openings of the masters: (as White, as Black), up to three per colour. Names are from the open openings table
# (src/services/openings.py); only what history has attached to the master: an opening bearing his name or his constant
# weapon. In a game the master goes into these lines when the opponent allows it, and names the opening in a remark.
SIGNATURE_OPENINGS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "kieseritzky": (("King's Gambit Accepted: Kieseritzky Gambit",), (KINGS_GAMBIT,)),
    "bird": (("Bird Opening",), ()),
    "wyvill": (("English Opening",), ()),
    "winawer": ((), ("French Defense: Winawer Variation",)),
    "albin": ((), ("Queen's Gambit Declined: Albin Countergambit",)),
    "alapin": (("Sicilian Defense: Alapin Variation",), ()),
    "grunfeld": ((QGD,), ("Grünfeld Defense",)),
    "pirc": ((), ("Pirc Defense",)),
    "caro": ((), ("Caro-Kann Defense",)),
    "colle": (("Queen's Pawn Game: Colle System",), ()),
    "samisch": (("Nimzo-Indian Defense: Sämisch Variation", "King's Indian Defense: Sämisch Variation"), ()),
    "torre": (("Queen's Pawn Game: Torre Attack",), ()),
    "ware": (("Ware Opening",), ("Dutch Defense: Stonewall Variation",)),
    "mieses": ((VIENNA, "Danish Gambit", "Center Game"), ()),
    "spielmann": ((VIENNA, KINGS_GAMBIT), ()),
    "charousek": ((KINGS_GAMBIT,), ()),
    "schlechter": ((RUY_LOPEZ,), ("Slav Defense",)),
    "maroczy": ((RUY_LOPEZ,), (FRENCH,)),
    "burn": ((), (FRENCH,)),
    "carls": (("English Opening",), ()),
    "blackburne": (("Scotch Game",), ()),
    "janowski": ((QGD,), ()),
    "bogoljubow": ((QGD,), ("Bogo-Indian Defense",)),
    "euwe": ((QGD,), ("Ruy Lopez: Open",)),
    "flohr": ((QGD,), ("Caro-Kann Defense",)),
    "fine": ((QGD,), ()),
    "reshevsky": ((QGD,), ("Nimzo-Indian Defense",)),
    "vidmar": ((QGD,), ("Queen's Gambit Declined: Orthodox Defense",)),
    "keres": ((RUY_LOPEZ,), ()),
    "kashdan": ((RUY_LOPEZ,), ()),
    "duras": ((RUY_LOPEZ,), ()),
    "teichmann": ((RUY_LOPEZ,), ("Queen's Gambit Declined: Orthodox Defense",)),
    "showalter": ((RUY_LOPEZ,), ()),
    "thomas": ((RUY_LOPEZ,), ()),
    "yates": ((RUY_LOPEZ,), ("King's Indian Defense",)),
    "canal": (("Italian Game: Giuoco Piano",), ()),
    "menchik": ((QGD,), (FRENCH,)),
    "becker": ((QGD,), ()),
    "alexander": ((), ("Dutch Defense",)),
    "dus_chotimirsky": ((QGD,), ()),
    "owen": ((), ("Owen Defense",)),
    "from": (("Danish Gambit",), ("Bird Opening: From's Gambit",)),
    # Variations named after the master himself (batch of 17.11, night).
    "szen": (("Sicilian Defense: Taimanov Variation, Szén Variation",), ()),
    "lowenthal": ((), ("Sicilian Defense: Löwenthal Variation",)),
    "horwitz": ((), ("Horwitz Defense",)),
    "mayet": (("Latvian Gambit: Mayet Attack",), ()),
    "kennedy_h": ((), ("Nimzowitsch Defense: Kennedy Variation",)),
    "gunsberg": (("Four Knights Game: Gunsberg Variation",), ()),
    "pollock": ((), ("Ruy Lopez: Pollock Defense",)),
    "mackenzie": (("Ruy Lopez: Morphy Defense, Mackenzie Variation",), ()),
    "mortimer": ((), ("Ruy Lopez: Berlin Defense, Anti-Berlin Variation, Mortimer Variation",)),
    "schallopp": ((), ("King's Gambit Accepted: Schallopp Defense",)),
    "berger": ((), ("Center Game: Berger Variation",)),
    "olland": (("French Defense: McCutcheon Variation, Dr. Olland Variation",), ()),
    "leonhardt": ((), ("Ponziani Opening: Leonhardt Variation",)),
    "levenfish": (("Sicilian Defense: Dragon Variation, Levenfish Variation",), ()),
    "bardeleben": ((), ("Vienna Game: Vienna Gambit, Bardeleben Variation",)),
    "bernstein": (("French Defense: McCutcheon Variation, Bernstein Variation",), ()),
    "stoltz": (("Semi-Slav Defense: Stoltz Variation",), ()),
    "stanley": (("Vienna Game: Stanley Variation",), ()),
    "raphael": (("Dutch Defense: Raphael Variation",), ()),
    "forgacs": (("Caro-Kann Defense: Forgacs Variation",), ()),
    "suchting": ((), ("Slav Defense: Süchting Variation",)),
    "breyer": (("King's Gambit Accepted: Breyer Gambit",), ()),
    "barnes": (("Barnes Opening",), ("Barnes Defense",)),
    "mongredien": (
        (),
        ("Modern Defense: Mongredien Defense, with Nc3", "Modern Defense: Mongredien Defense, with Nf3",),
    ),
    "rousseau": ((), ("Italian Game: Rousseau Gambit",)),
    "hromadka": ((), ("Benoni Defense: Hromádka System",)),
    "metger": ((), ("Four Knights Game: Spanish Variation, Symmetrical Variation, Metger Unpin",)),
    "kmoch": (("Nimzo-Indian Defense: Kmoch Variation",), ()),
    "romih": ((), ("Semi-Slav Defense: Romih Variation",)),
    "levitsky": (("Queen's Pawn Game: Levitsky Attack",), ()),
    "macleod": (("King's Pawn Game: MacLeod Attack",), ()),
    "hanham": ((), ("Philidor Defense: Hanham Variation",)),
    "moller": ((), ("Ruy Lopez: Morphy Defense, Møller Variation",)),
}


def opening_position(name: str) -> str:
    """Position (EPD) of an opening by name from the open table: the shortest line with such a name."""
    found = [line for line in openings.lines().values() if line.name == name]
    if not found:
        raise KeyError(f"no opening named {name!r} in the table")
    return min(found, key=lambda line: len(line.moves)).epd


def _guest(guest_id: str, pgn_name: str, era: str | None, rating: int, **style) -> Guest:
    """Master of the past: personality from the style sliders, target_elo = rating, signature openings from
    SIGNATURE_OPENINGS."""
    white, black = SIGNATURE_OPENINGS.get(guest_id, ((), ()))
    config = BotPersonalityConfig(
        target_elo=rating, openings_white=[opening_position(name) for name in white],
        openings_black=[opening_position(name) for name in black], **style,
    )
    return Guest(guest_id, pgn_name, era, rating, config)


# The field by tournament (headings below); strength is a historical estimate relative to the calibrated masters. The comment
# on
# each master says what his style is or what he is known for.
GUESTS: tuple[Guest, ...] = (
    # --- London 1851: the first international tournament -------------------------------------------------------
    # King's Gambit and attack with no regard for material.
    _guest("kieseritzky", "Kieseritzky, Lionel", "1806–1853", 1950, aggression=80, mobility=150, king_safety=70,
           randomness=30, opening_style="gambit", draw_attitude=-50),
    # A master of pawn endgames, cautious play.
    _guest("szen", "Szen, Jozsef", "1805–1857", 1950, aggression=-30, pawn_structure=160, passed_pawns=170,
           king_safety=130, randomness=15),
    # An opening theorist, stubborn defence.
    _guest("lowenthal", "Loewenthal, Johann", "1810–1876", 1950, aggression=-10, center_control=140, king_safety=130,
           randomness=20),
    # A composer of studies: combinations and precise endgames.
    _guest("horwitz", "Horwitz, Bernhard", "1807–1885", 1900, aggression=40, mobility=140, passed_pawns=140,
           randomness=25),
    # Slow closed play, grinding the opponent down.
    _guest("williams", "Williams, Elijah", "1809–1854", 1900, aggression=-50, king_safety=160, pawn_structure=150,
           randomness=20, draw_attitude=20),
    # Positional play, the English Opening.
    _guest("wyvill", "Wyvill, Marmaduke", "1815–1896", 1900, aggression=-20, pawn_structure=160, center_control=130,
           randomness=20),
    # Unusual openings, risk and invention.
    _guest("bird", "Bird, Henry Edward", "1829–1908", 1950, aggression=70, mobility=150, king_safety=70,
           randomness=35, draw_attitude=-60),
    _guest("mayet", "Mayet, Carl", "1810–1868", 1800, aggression=40, mobility=130, randomness=35),
    _guest("kennedy_h", "Kennedy, Hugh Alexander", "1809–1878", 1800, aggression=20, mobility=120, randomness=35),
    _guest("lowe", "Loewe, Edward", "1794–1880", 1750, aggression=-10, king_safety=120, randomness=40),
    _guest("newham", "Newham, Samuel", None, 1700, aggression=0, randomness=40),
    _guest("kennedy_e", "Kennedy, Edward Shirley", "1817–1898", 1650, aggression=10, randomness=45),
    _guest("brodie", "Brodie, Alfred", None, 1650, aggression=0, randomness=45),
    _guest("mucklow", "Mucklow, James R.", None, 1600, aggression=0, randomness=50, habits=["pawn_grabber"]),

    # --- Hastings 1895 ------------------------------------------------------------------------------------------
    # Flawless defence, the draw as a weapon.
    _guest("schlechter", "Schlechter, Carl", "1874–1918", 2200, aggression=-20, king_safety=160, pawn_structure=150,
           randomness=8, blunder_guard_cp=70, draw_attitude=50),
    # Positional pressure and open files.
    _guest("teichmann", "Teichmann, Richard", "1868–1925", 2150, aggression=10, mobility=150, center_control=140,
           randomness=12, draw_attitude=20),
    # Two bishops and attack, does not recognise draws.
    _guest("janowski", "Janowski, David", "1868–1927", 2150, aggression=90, mobility=170, king_safety=60,
           randomness=25, draw_attitude=-90),
    # A tactician and endgame master.
    _guest("blackburne", "Blackburne, Joseph Henry", "1841–1924", 2100, aggression=70, mobility=150, passed_pawns=130,
           randomness=20, draw_attitude=-40),
    # Stubborn defence.
    _guest("burn", "Burn, Amos", "1848–1925", 2100, aggression=-50, king_safety=170, pawn_structure=150, randomness=12),
    # The attacking school, a teacher of Russian masters.
    _guest("schiffers", "Schiffers, Emanuel", "1850–1904", 2050, aggression=50, mobility=140, randomness=20),
    # An openings connoisseur, cautious play.
    _guest("bardeleben", "Bardeleben, Curt von", "1861–1924", 2050, aggression=-20, center_control=150,
           pawn_structure=140, randomness=15, draw_attitude=30),
    # Calm positional play.
    _guest("mason", "Mason, James", "1849–1905", 2050, aggression=-20, pawn_structure=150, king_safety=130,
           randomness=20),
    # A practical player, cunning defence.
    _guest("gunsberg", "Gunsberg, Isidor", "1854–1930", 2050, aggression=20, mobility=130, king_safety=120,
           randomness=20),
    # Gambits and sharp play.
    _guest("mieses", "Mieses, Jacques", "1865–1954", 2050, aggression=90, mobility=160, king_safety=60,
           randomness=30, opening_style="gambit", draw_attitude=-70),
    _guest("walbrodt", "Walbrodt, Carl August", "1871–1902", 2000, aggression=20, mobility=130, randomness=25),
    # An analyst: order and precision.
    _guest("marco", "Marco, Georg", "1863–1923", 2000, aggression=-20, pawn_structure=140, king_safety=130,
           randomness=20, draw_attitude=20),
    # Counter-gambit and bold sacrifices.
    _guest("albin", "Albin, Adolf", "1848–1920", 1950, aggression=70, mobility=140, randomness=30,
           opening_style="gambit"),
    _guest("pollock", "Pollock, William Henry Krause", "1859–1896", 1900, aggression=70, mobility=140, king_safety=70,
           randomness=35, draw_attitude=-40),
    _guest("tinsley", "Tinsley, Samuel", "1847–1903", 1850, aggression=10, randomness=35),
    _guest("vergani", "Vergani, Beniamino", "1863–1927", 1700, aggression=0, randomness=45),

    # --- St Petersburg 1914 ------------------------------------------------------------------------------------
    # Resourcefulness and calculation.
    _guest("bernstein", "Bernstein, Ossip", "1882–1962", 2200, aggression=40, mobility=150, center_control=130,
           randomness=15),

    # --- New York 1924 -------------------------------------------------------------------------------------------
    # Defence and queen endgames.
    _guest("maroczy", "Maroczy, Geza", "1870–1951", 2250, aggression=-40, king_safety=170, pawn_structure=160,
           randomness=8, blunder_guard_cp=70, draw_attitude=30),
    # Optimism and initiative.
    _guest("bogoljubow", "Bogoljubow, Efim", "1889–1952", 2250, aggression=60, mobility=160, center_control=140,
           randomness=20, draw_attitude=-50),
    # A dangerous attacking player.
    _guest("yates", "Yates, Frederick Dewhurst", "1884–1932", 2050, aggression=70, mobility=150, king_safety=70,
           randomness=25, draw_attitude=-40),
    _guest("lasker_edward", "Lasker, Edward", "1885–1981", 2050, aggression=30, mobility=140, randomness=20),

    # --- AVRO 1938 -----------------------------------------------------------------------------------------------
    # An all-rounder: attack and precise technique.
    _guest("keres", "Keres, Paul", "1916–1975", 2400, aggression=60, mobility=170, center_control=140, randomness=10,
           blunder_guard_cp=60, draw_attitude=-30),
    # A clear plan and technique.
    _guest("fine", "Fine, Reuben", "1914–1993", 2400, aggression=0, mobility=150, pawn_structure=150, randomness=8,
           blunder_guard_cp=60),
    # Logic and calculation.
    _guest("euwe", "Euwe, Max", "1901–1981", 2350, aggression=30, center_control=150, mobility=150, randomness=15),
    # Tenacious defence and endurance in difficult positions.
    _guest("reshevsky", "Reshevsky, Samuel", "1911–1992", 2400, aggression=-10, king_safety=160, pawn_structure=150,
           randomness=10, blunder_guard_cp=60, draw_attitude=-20),
    # Positional play and endgames.
    _guest("flohr", "Flohr, Salo", "1908–1983", 2350, aggression=-40, pawn_structure=170, passed_pawns=150,
           king_safety=140, randomness=8, blunder_guard_cp=60, draw_attitude=40),

    # --- Second batch of tournaments (28.4): Baden-Baden 1870, London 1883, San Sebastian 1911, New York 1927, Nottingham 1936
    # ---
    # Classical clear play.
    _guest("neumann", "Neumann, Gustav", "1838–1881", 2050, aggression=10, center_control=140, randomness=15),
    # Natural talent, light piece play.
    _guest("de_vere", "De Vere, Cecil Valentine", "1846–1875", 1950, aggression=0, mobility=140, randomness=25),
    # Resourcefulness in attack and in the endgame.
    _guest("winawer", "Winawer, Szymon", "1838–1919", 2100, aggression=50, mobility=150, randomness=25),
    # Open play.
    _guest("rosenthal", "Rosenthal, Samuel", "1837–1902", 2000, aggression=30, mobility=130, randomness=25),
    _guest("minckwitz", "Minckwitz, Johannes", "1843–1901", 1950, aggression=20, randomness=30),
    # Attack on the king.
    _guest("mackenzie", "Mackenzie, George Henry", "1837–1891", 2100,
           aggression=70, mobility=150, king_safety=80, randomness=20, draw_attitude=-40),
    # Solidity: he is very hard to beat.
    _guest("englisch", "Englisch, Berthold", "1851–1897", 2050,
           aggression=-40, king_safety=160, pawn_structure=140, randomness=12, draw_attitude=60),
    _guest("noa", "Noa, Josef", "1856–1903", 1900, aggression=0, randomness=35),
    _guest("sellman", "Sellman, Alexander", "1856–1888", 1850, aggression=10, randomness=35),
    _guest("mortimer", "Mortimer, James", "1832–1911", 1750, aggression=20, randomness=45),
    _guest("skipworth", "Skipworth, Arthur", "1830–1898", 1750, aggression=0, randomness=45),
    # Solid positional play.
    _guest("vidmar", "Vidmar, Milan", "1885–1962", 2250,
           aggression=-10, pawn_structure=150, center_control=140, randomness=10),
    # Attack and sacrifice.
    _guest("spielmann", "Spielmann, Rudolf", "1883–1942", 2250,
           aggression=90, mobility=160, king_safety=60, randomness=20, opening_style="gambit", draw_attitude=-50),
    # A resourceful fighter, a composer of studies.
    _guest("duras", "Duras, Oldrich", "1882–1957", 2200, aggression=50, mobility=150, passed_pawns=130, randomness=20),
    # An opening theorist.
    _guest("leonhardt", "Leonhardt, Paul Saladin", "1877–1934", 2100, aggression=40, center_control=140, randomness=25),
    _guest("tylor", "Tylor, Theodore", "1900–1968", 2050, aggression=-10, king_safety=130, randomness=20),
    # Attacking style.
    _guest("alexander", "Alexander, Conel Hugh O'Donel", "1909–1974", 2150,
           aggression=70, mobility=150, randomness=20, draw_attitude=-40),
    _guest("thomas", "Thomas, George Alan", "1881–1972", 2100, aggression=-10, pawn_structure=140, randomness=20),
    _guest("winter", "Winter, William", "1897–1955", 2050, aggression=30, mobility=130, randomness=25),

    # --- Third batch of tournaments (28.4): Vienna 1882, Nuremberg 1896, London 1899, Monte Carlo 1903 ------------------
    _guest("wittek", "Wittek, Alexander", "1852–1894", 2050, aggression=30, mobility=130, randomness=25),
    # Cautious positional play.
    _guest("weiss", "Weiss, Max", "1857–1927", 2100,
           aggression=-30, king_safety=150, pawn_structure=150, randomness=12, draw_attitude=40),
    _guest("hruby", "Hruby, Vincenz", "1856–1917", 2000, aggression=10, randomness=25),
    _guest("schwarz", "Schwarz, Adolf", "1836–1910", 2000, aggression=-20, king_safety=140, randomness=20),
    _guest("meitner", "Meitner, Philipp", "1839–1910", 1950, aggression=20, randomness=30),
    # Whimsical openings.
    _guest("ware", "Ware, Preston", "1821–1890", 1850, aggression=10, randomness=40),
    _guest("fleissig", "Fleissig, Bernhard", "1853–1931", 1900, aggression=0, randomness=30),
    # A brilliant attacking talent, gambits.
    _guest("charousek", "Charousek, Rudolf", "1873–1900", 2200,
           aggression=80, mobility=160, randomness=20, opening_style="gambit", draw_attitude=-50),
    _guest("showalter", "Showalter, Jackson Whipps", "1859–1935", 2100, aggression=50, mobility=140, randomness=25),
    _guest("porges", "Porges, Moritz", "1857–1909", 2000, aggression=0, center_control=130, randomness=25),
    # Lively attacking play.
    _guest("schallopp", "Schallopp, Emil", "1843–1919", 2000, aggression=60, mobility=140, randomness=30),
    _guest("cohn", "Cohn, Wilhelm", "1859–1913", 2050, aggression=10, randomness=25),
    _guest("lee", "Lee, Francis Joseph", "1858–1909", 1950, aggression=-10, king_safety=130, randomness=25),
    # Solid play.
    _guest("wolf", "Wolf, Heinrich", "1875–1943", 2100,
           aggression=-20, king_safety=140, randomness=15, draw_attitude=40),
    _guest("taubenhaus", "Taubenhaus, Jean", "1850–1919", 2000, aggression=20, randomness=30),
    _guest("reggio", "Reggio, Arturo", "1863–1917", 1900, aggression=0, randomness=35),
    # Lost all 26 games at Monte Carlo 1903.
    _guest("moreau", "Moreau, Charles", "1837–1916", 1500, aggression=0, randomness=60, habits=["hangs_pieces"]),

    # --- Fourth batch of tournaments (28.4): Karlsbad 1907, Moscow 1925, Karlsbad 1929, Bled 1931 ------------------
    # Solid positional play.
    _guest("salwe", "Salwe, Georg", "1862–1920", 2150, aggression=-10, pawn_structure=140, randomness=15),
    # Attack and risk.
    _guest("dus_chotimirsky", "Dus-Chotimirsky, Fyodor", "1881–1965", 2050, aggression=60, mobility=150, randomness=30),
    # An endgame theorist.
    _guest("berger", "Berger, Johann", "1845–1933", 2050,
           aggression=-30, pawn_structure=150, passed_pawns=160, randomness=15, draw_attitude=40),
    _guest("olland", "Olland, Adolf", "1867–1933", 1950, aggression=10, randomness=25),
    _guest("cohn_erich", "Cohn, Erich", "1884–1918", 2050, aggression=30, randomness=25),
    _guest("johner_paul", "Johner, Paul", "1887–1938", 2100, aggression=10, mobility=130, randomness=20),
    # Sharp tactical play.
    _guest("torre", "Torre Repetto, Carlos", "1904–1978", 2250, aggression=50, mobility=160, randomness=20),
    _guest("romanovsky", "Romanovsky, Peter", "1892–1964", 2200, aggression=40, mobility=150, randomness=20),
    # An openings connoisseur, cautious play.
    _guest("grunfeld", "Gruenfeld, Ernst", "1893–1962", 2250,
           aggression=-30, center_control=140, pawn_structure=150, randomness=10, draw_attitude=40),
    _guest("ilyin_zhenevsky", "Ilyin-Zhenevsky, Alexander", "1894–1941", 2150, aggression=30, randomness=25),
    _guest("bohatyrchuk", "Bohatyrchuk, Fedir", "1892–1984", 2250, aggression=20, center_control=140, randomness=15),
    _guest("verlinsky", "Verlinsky, Boris", "1888–1950", 2200, aggression=50, mobility=150, randomness=25),
    _guest("levenfish", "Levenfish, Grigory", "1889–1961", 2300,
           aggression=30, mobility=150, center_control=130, randomness=15),
    _guest("rabinovich", "Rabinovich, Ilya", "1891–1942", 2200, aggression=-10, pawn_structure=150, randomness=15),
    _guest("samisch", "Saemisch, Friedrich", "1896–1975", 2200, aggression=20, center_control=140, randomness=20),
    _guest("gotthilf", "Gotthilf, Solomon", "1903–1967", 2100, aggression=0, randomness=25),
    _guest("zubarev", "Zubarev, Nikolai", "1894–1951", 2100, aggression=10, randomness=25),
    _guest("becker", "Becker, Albert", "1896–1984", 2200,
           aggression=-20, pawn_structure=140, randomness=15, draw_attitude=30),
    # Combinational play.
    _guest("canal", "Canal, Esteban", "1896–1981", 2200, aggression=60, mobility=150, randomness=25),
    # A composer of studies, strong endgame.
    _guest("mattison", "Matisons, Hermanis", "1894–1932", 2200,
           aggression=0, passed_pawns=150, pawn_structure=140, randomness=15),
    # Attack by his own system.
    _guest("colle", "Colle, Edgard", "1897–1932", 2200, aggression=50, mobility=140, king_safety=90, randomness=20),
    _guest("treybal", "Treybal, Karel", "1885–1941", 2150, aggression=40, randomness=25),
    _guest("gilg", "Gilg, Karl", "1901–1981", 2150, aggression=10, randomness=25),
    # The first women's world champion; positional style.
    _guest("menchik", "Menchik, Vera", "1906–1944", 2050,
           aggression=-10, pawn_structure=140, king_safety=130, randomness=20),
    # Technique and endgames.
    _guest("kashdan", "Kashdan, Isaac", "1905–1985", 2350,
           aggression=10, mobility=150, pawn_structure=140, randomness=10),
    _guest("stoltz", "Stoltz, Goesta", "1904–1963", 2250, aggression=60, mobility=150, randomness=20),
    _guest("kostic", "Kostic, Boris", "1887–1963", 2200, aggression=30, mobility=140, randomness=20),
    _guest("asztalos", "Asztalos, Lajos", "1889–1956", 2150, aggression=0, randomness=20),
    _guest("pirc", "Pirc, Vasja", "1907–1980", 2250, aggression=10, center_control=120, mobility=140, randomness=15),

    # --- Fifth batch of tournaments (28.4): New York 1857, Paris 1878, Paris 1900, St Petersburg 1909 ---------------------
    _guest("stanley", "Stanley, Charles Henry", "1819–1901", 1900, aggression=20, mobility=130, randomness=30),
    _guest("lichtenhein", "Lichtenhein, Theodor", "1829–1874", 1900, aggression=30, mobility=130, randomness=30),
    _guest("marache", "Marache, Napoleon", "1818–1875", 1850, aggression=40, mobility=130, randomness=35),
    _guest("raphael", "Raphael, Benjamin", "1818–1880", 1800, aggression=10, randomness=35),
    _guest("perrin", "Perrin, Frederick", "1815–1889", 1800, aggression=0, randomness=35),
    _guest("thompson", "Thompson, James", "1804–1870", 1800, aggression=30, randomness=35),
    _guest("montgomery", "Montgomery, Hardman Philips", None, 1800, aggression=10, randomness=35),
    _guest("meek", "Meek, Alexander Beaufort", "1814–1865", 1750, aggression=20, randomness=40),
    _guest("fuller", "Fuller, William James Appleton", None, 1750, aggression=10, randomness=40),
    # A congress organiser.
    _guest("fiske", "Fiske, Daniel Willard", "1831–1904", 1700, aggression=0, randomness=40),
    _guest("calthrop", "Calthrop, Samuel Robert", None, 1700, aggression=0, randomness=40),
    _guest("kennicott", "Kennicott, Hiram", None, 1700, aggression=10, randomness=40),
    _guest("knott", "Knott, Hubert", None, 1700, aggression=0, randomness=40),
    _guest("allison", "Allison, William", None, 1650, aggression=0, randomness=45),
    _guest("clerc", "Clerc, Albert", "1830–1918", 1950, aggression=10, randomness=30),
    _guest("pitschel", "Pitschel, Karl", "1829–1883", 1800, aggression=0, randomness=40),
    _guest("gifford", "Gifford, H. W. B.", "1847–1924", 1750, aggression=0, randomness=45),
    _guest("brody", "Brody, Miklos", "1877–1949", 2000, aggression=10, randomness=30),
    _guest("rosen", "Rosen, Leon", "1869–1942", 1800, aggression=0, randomness=40),
    _guest("sterling", "Marquez Sterling, Manuel", "1872–1934", 1700, aggression=10, randomness=45),
    _guest("didier", "Didier, M.", None, 1650, aggression=0, randomness=45),
    _guest("perlis", "Perlis, Julius", "1880–1913", 2150, aggression=20, mobility=140, randomness=20),
    _guest("forgacs", "Forgacs, Leo", "1881–1930", 2150, aggression=30, mobility=140, randomness=20),
    _guest("speijer", "Speijer, Abraham", "1873–1956", 2000, aggression=0, randomness=25),
    _guest("freymann", "Freymann, Sergey von", "1882–1946", 2050, aggression=10, randomness=25),
    _guest("znosko_borovsky", "Znosko-Borovsky, Eugene", "1884–1954", 2100, aggression=30, mobility=140, randomness=25),

    # --- Sixth batch of tournaments (28.4): Vienna 1898, Karlsbad 1911, Mannheim 1914, Karlsbad 1923 --------------------
    _guest("lipke", "Lipke, Paul", "1870–1955", 2100, aggression=20, mobility=130, randomness=20),
    # An opening theorist.
    _guest("alapin", "Alapin, Simon", "1856–1923", 2100, aggression=20, center_control=130, randomness=25),
    _guest("halprin", "Halprin, Alexander", "1868–1921", 2000, aggression=50, randomness=30),
    _guest("caro", "Caro, Horatio", "1862–1920", 2000, aggression=10, randomness=25),
    _guest("baird", "Baird, David Graham", "1854–1913", 1850, aggression=0, randomness=35),
    _guest("trenchard", "Trenchard, Herbert William", "1857–1934", 1800, aggression=0, randomness=40),
    _guest("rotlewi", "Rotlewi, Gersz", "1889–1920", 2200, aggression=40, mobility=150, randomness=20),
    _guest("suchting", "Suechting, Hugo", "1874–1916", 2050, aggression=-20, king_safety=140, randomness=20),
    _guest("rabinovich_abram", "Rabinovich, Abram", "1878–1943", 2050, aggression=30, randomness=25),
    _guest("chajes", "Chajes, Oscar", "1873–1928", 2050, aggression=40, randomness=25),
    _guest("fahrni", "Fahrni, Hans", "1874–1939", 2050, aggression=10, randomness=25),
    _guest("jaffe", "Jaffe, Charles", "1879–1941", 2050, aggression=30, randomness=30),
    # One of the founders of hypermodernism.
    _guest("breyer", "Breyer, Gyula", "1893–1921", 2200,
           aggression=30, center_control=120, mobility=150, randomness=20),
    _guest("john", "John, Walter", "1879–1940", 2050, aggression=0, randomness=25),
    _guest("post", "Post, Ehrhardt", "1881–1947", 2100, aggression=10, randomness=20),
    _guest("carls", "Carls, Carl", "1880–1958", 2100, aggression=-10, center_control=130, randomness=20),
    _guest("kruger", "Krueger, Paul", "1871–1939", 2000, aggression=0, randomness=30),
    _guest("flamberg", "Flamberg, Alexander", "1880–1926", 2100, aggression=30, randomness=25),
    _guest("bernstein_jacob", "Bernstein, Jacob", "1885–1959", 2000, aggression=10, randomness=25),

    # --- Seventh batch of tournaments (28.4): London 1862, Paris 1867 -------------------------------------------------
    _guest("owen", "Owen, John", "1827–1901", 1950, aggression=0, pawn_structure=130, randomness=30),
    _guest("macdonnell", "MacDonnell, George Alcock", "1830–1899", 1950, aggression=30, mobility=130, randomness=30),
    _guest("dubois", "Dubois, Serafino", "1817–1899", 2000, aggression=30, mobility=140, randomness=25),
    _guest("barnes", "Barnes, Thomas Wilson", "1825–1874", 1950, aggression=10, randomness=30),
    _guest("hannah", "Hannah, James", None, 1800, aggression=10, randomness=40),
    _guest("robey", "Robey, James", None, 1750, aggression=0, randomness=45),
    _guest("deacon", "Deacon, Frederick", "1829–1875", 1800, aggression=10, randomness=40),
    _guest("mongredien", "Mongredien, Augustus", "1807–1888", 1750, aggression=0, randomness=45),
    _guest("green", "Green, Valentine", None, 1750, aggression=0, randomness=45),
    # A combinational player.
    _guest("kolisch", "Kolisch, Ignatz von", "1837–1889", 2100,
           aggression=60, mobility=150, randomness=20, draw_attitude=-40),
    _guest("riviere", "Riviere, Jules Arnous de", "1830–1905", 1950, aggression=30, mobility=130, randomness=30),
    _guest("golmayo", "Golmayo Zupide, Celso", "1820–1898", 1900, aggression=20, randomness=30),
    _guest("czarnowski", "Czarnowski, Hieronim", "1834–1902", 1850, aggression=10, randomness=35),
    # An inventor of puzzles; risky in practical play.
    _guest("loyd", "Loyd, Samuel", "1841–1911", 1850, aggression=40, mobility=130, randomness=40),
    _guest("dandre", "d'Andre, Emile", None, 1800, aggression=0, randomness=40),
    # Gambit style.
    _guest("from", "From, Martin Severin", "1828–1895", 1850,
           aggression=50, mobility=130, randomness=35, opening_style="gambit"),
    _guest("rousseau", "Rousseau, Eugene", "1805–1877", 1800, aggression=20, randomness=40),

    # --- Eighth batch of tournaments (28.4): Berlin 1881 — Moravska Ostrava 1923 -------------------------------------
    # Elder brother of Louis Paulsen.
    _guest("paulsen_w", "Paulsen, Wilfried", "1828–1901", 1950, aggression=-10, king_safety=130, randomness=30),
    _guest("riemann", "Riemann, Fritz", "1859–1932", 2000, aggression=40, mobility=130, randomness=25),
    # Year of birth in the source — "around 1845".
    _guest("wemmers", "Wemmers, Carl", "1845–1882", 1900, aggression=10, randomness=35),
    _guest("schmid", "Schmid, Carl Friedrich", "1840–1897", 1850, aggression=0, randomness=40),
    # Years of life unknown.
    _guest("schutz", "Schuetz, H. von", None, 1650, aggression=0, randomness=45),
    # Not to be confused with Adolf Schwarz (schwarz).
    _guest("schwarz_jacques", "Schwarz, Jacques", "1856–1921", 1950, aggression=0, randomness=30),
    _guest("fox", "Fox, Albert Whiting", "1881–1964", 2000, aggression=50, mobility=140, randomness=30),
    # Years of life — per Wikidata (Q11727884).
    _guest("barry", "Barry, John Finan", "1873–1940", 2000, aggression=40, randomness=30),
    _guest("napier", "Napier, William Ewart", "1881–1952", 2050, aggression=50, mobility=140, randomness=25),
    # Years of life not confirmed by a source; in 1904 he was 33.
    _guest("lawrence", "Lawrence, Thomas", None, 1950, aggression=0, randomness=30),
    _guest("hodges", "Hodges, Albert Beauregard", "1861–1944", 2000, aggression=10, randomness=30),
    _guest("delmar", "Delmar, Eugene", "1841–1909", 1900, aggression=20, randomness=35),
    _guest("swiderski", "Swiderski, Rudolf", "1878–1909", 2100, aggression=30, mobility=130, randomness=25),
    # A composer of studies.
    _guest("prokes", "Prokes, Ladislav", "1884–1966", 1950, aggression=10, passed_pawns=150, randomness=30),
    _guest("kvicala", "Kvicala, Jan", "1868–1939", 1900, aggression=0, randomness=35),
    # Not to be confused with Karel Traybal (treybal).
    _guest("treybal_frantisek", "Treybal, Frantisek", "1882–1947", 2000, aggression=20, randomness=30),
    _guest("kohnlein", "Koehnlein, Friedrich", "1879–1916", 2000, aggression=20, randomness=30),
    # A composer of studies.
    _guest("selezniev", "Selezniev, Alexey", "1888–1967", 2150,
           aggression=-10, passed_pawns=150, pawn_structure=130, randomness=20),
    _guest("pokorny", "Pokorny, Amos", "1890–1949", 2050, aggression=10, randomness=25),
    _guest("hromadka", "Hromadka, Karel", "1887–1956", 2050, aggression=50, mobility=140, randomness=30),
    _guest("walter", "Walter, Max", "1899–1940", 1950, aggression=10, randomness=30),

    # --- Ninth batch of tournaments (28.4): Berlin 1897, San Remo 1930 ----------------------------------------------
    _guest("metger", "Metger, Johannes", "1850–1926", 2000, aggression=0, pawn_structure=130, randomness=30),
    _guest("zinkl", "Zinkl, Adolf", "1871–1944", 1950, aggression=10, randomness=30),
    _guest("ahues", "Ahues, Carl", "1883–1968", 2150, aggression=20, mobility=130, randomness=20),
    # A chess writer; known for his books.
    _guest("kmoch", "Kmoch, Hans", "1894–1973", 2150, aggression=-10, pawn_structure=150, randomness=20),
    _guest("araiza", "Araiza, Jose Joaquin", "1900–1971", 2000, aggression=20, randomness=30),
    _guest("monticelli", "Monticelli, Mario", "1902–1995", 2150, aggression=30, mobility=130, randomness=25),
    _guest("grau", "Grau, Roberto", "1900–1944", 2100, aggression=10, center_control=130, randomness=25),
    _guest("romih", "Romih, Max", "1893–1979", 2000, aggression=10, randomness=30),

    # --- Tenth batch of tournaments (28.4): New York 1889, Kiev 1903 ------------------------------------------------
    _guest("lipschutz", "Lipschuetz, Samuel", "1863–1905", 2150, aggression=10, pawn_structure=130, randomness=20),
    _guest("judd", "Judd, Max", "1851–1906", 2050, aggression=20, randomness=25),
    _guest("burille", "Burille, Constant Ferdinand", "1866–1914", 1950, aggression=10, randomness=30),
    # A major in the Union army; the Hanham variation in the Philidor Defence.
    _guest("hanham", "Hanham, James Moore", "1840–1923", 1950, aggression=-20, king_safety=130, randomness=30),
    _guest("gossip", "Gossip, George H. D.", "1841–1907", 1900, aggression=20, randomness=35),
    _guest("martinez", "Martinez, Dion", "1837–1928", 1950, aggression=20, randomness=30),
    # Brother of David Graham Baird (baird).
    _guest("baird_john", "Baird, John Washington", "1852–1923", 1850, aggression=0, randomness=35),
    _guest("macleod", "MacLeod, Nicholas", "1870–1965", 1800, aggression=20, randomness=40),
    # Years of life not confirmed by a source.
    _guest("yurevich", "Yurevich, Vladimir", None, 2100, aggression=20, randomness=25),
    _guest("lowtzky", "Lowtzky, Moishe", "1880–1940", 2100, aggression=20, mobility=130, randomness=25),
    # Levitsky Attack: 1.d4 d5 2.Bg5.
    _guest("levitsky", "Levitsky, Stepan", "1876–1924", 2100, aggression=30, mobility=130, randomness=25),
    _guest("izbinsky", "Izbinsky, Stefan", "1884–1912", 2000, aggression=20, randomness=30),
    _guest("lebedev", "Lebedev, Sergey", "1868–1942", 2000, aggression=0, randomness=30),
    # Years of life unknown.
    _guest("kulomzin", "Kulomzin, Viacheslav", None, 1950, aggression=0, randomness=30),
    # Years of life unknown.
    _guest("kalinsky", "Kalinsky, N.", None, 1900, aggression=0, randomness=35),
    # A Kiev player; years of life unknown.
    _guest("benko", "Benko, P. P.", None, 1900, aggression=0, randomness=35),
    # A Kiev player; years of life unknown.
    _guest("nikolaev", "Nikolaev, Boris", None, 1800, aggression=0, randomness=40),
    # Died in 1905, year of birth unknown.
    _guest("stamm", "Stamm, Wilhelm von", None, 1700, aggression=0, randomness=40),
    # A Kiev player; withdrew from the 1903 tournament. Years of life unknown.
    _guest("breev", "Breev, V. V.", None, 1600, aggression=0, randomness=45),

    # --- Twelfth batch of tournaments (28.4): London 1922, Baden-Baden 1925, Semmering 1926 -----------------------
    _guest("atkins", "Atkins, Henry Ernest", "1872–1955", 2150, aggression=-10, pawn_structure=140, randomness=20),
    _guest("wahltuch", "Wahltuch, Victor", "1875–1953", 1950, aggression=20, randomness=30),
    _guest("watson", "Watson, Charles G. M.", "1878–1961", 1950, aggression=10, randomness=30),
    _guest("morrison", "Morrison, John Stuart", "1889–1975", 1950, aggression=0, randomness=30),
    _guest("marotti", "Marotti, Davide", "1881–1940", 1850, aggression=0, randomness=35),
    _guest("rosselli", "Rosselli del Turco, Stefano", "1877–1947", 2000, aggression=10, randomness=30),
    _guest("kolste", "Kolste, Jan Willem te", "1874–1936", 1850, aggression=0, randomness=35),
    _guest("vajda", "Vajda, Arpad", "1896–1967", 2100, aggression=-10, king_safety=130, randomness=20),
    _guest("davidson", "Davidson, Jacques", "1890–1969", 2000, aggression=20, randomness=30),
    _guest("michel", "Michel, Walter", "1888–1969", 1950, aggression=0, randomness=30),

    # --- Thirteenth batch of tournaments (28.4): Gothenburg 1920, Vienna 1922 --------------------------------------------
    _guest("moller", "Moeller, Joergen", "1873–1944", 2000, aggression=30, mobility=130, randomness=30),
    _guest("vukovic", "Vukovic, Vladimir", "1898–1975", 2050, aggression=40, mobility=130, randomness=25),
    _guest("takacs", "Takacs, Sandor", "1893–1932", 2050, aggression=10, randomness=25),
    _guest("konig", "Koenig, Imre", "1901–1992", 2000, aggression=0, randomness=30),

    # --- Fourteenth batch of tournaments (28.4): Copenhagen 1923 ---------------------------------------------------
    # Died two weeks after the Copenhagen tournament.
    _guest("jacobsen", "Jacobsen, Egil", "1897–1923", 2000, aggression=20, randomness=30),
)
# Lookup by id (the guest:<id> key without the prefix).
GUESTS_BY_ID = {guest.id: guest for guest in GUESTS}
# By the name from PGN ("Surname, Given name"): under it a game with a master is saved and shown in the archive.
GUESTS_BY_PGN_NAME = {guest.pgn_name: guest for guest in GUESTS}
