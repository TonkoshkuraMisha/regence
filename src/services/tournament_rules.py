# --- FILE: src/services/tournament_rules.py ---
"""
Tournament rules (tasks 15.1, 15.4, 28.1) - pure functions, without database, network or engine; they read no data.
Applied by tournaments.py (the course of a tournament), time_machine.py (size limits) and src/services/arena.py.

The participant number (seat) is their seeding: 1 is the strongest by rating at the start.

Round robin (4, 6, 8 participants): the schedule follows the FIDE Berger tables. Places: points, then the head-to-head result
among those tied, then the Sonneborn-Berger coefficient; if equal on that too - the higher seed ranks higher.

Knockout (4, 8): the bracket by seeding (1-8, 4-5, 2-7, 3-6 - the first and second seeds meet only in the final).
A match is one game, the higher seed plays White. A draw means a replay with colours swapped and a time control half as long;
another draw - a deciding game in which a draw is enough for Black; Black is played by the higher seed (a reward for seeding).
Places: the winner is 1, the finalist 2, the semi-final losers share 3rd, the quarter-final losers 5th.

Big tournaments ("Time Machine", task 28.1 - famous tournaments of the past with the full field): a round robin for any
number of participants up to 28 (Carlsbad 1911: twenty-six masters and the player; with an odd number everyone sits out
one round) and in several rounds with colours swapped (round_robin_schedule); a bracket for any number of participants -
the strongest seeds skip the first round without playing (bracket_slots). The player's ordinary tournaments are still
limited to the sizes below.
"""

from dataclasses import dataclass
from typing import Literal

Result = Literal["1-0", "0-1", "1/2-1/2"]
Stage = Literal["main", "rematch", "armageddon"]

# Allowed number of participants of an ordinary player tournament (including the player).
ROUND_ROBIN_SIZES = (4, 6, 8)
KNOCKOUT_SIZES = (4, 8)
# Swiss system (task 15.4): size -> number of rounds.
SWISS_SIZES = (6, 8)
SWISS_ROUNDS = {6: 4, 8: 5}
# Lower bound of the base time for a replay and a deciding game: the control is no shorter than a minute.
MIN_SHORTENED_BASE_MS = 60_000
# Tournaments with a historical field: size limits (round robin - up to 28 participants, bracket - up to 33) and number of
# circuits.
OPEN_ROUND_ROBIN_SIZES = range(3, 29)
OPEN_KNOCKOUT_SIZES = range(3, 34)
MAX_CYCLES = 6


# --- Round robin ---------------------------------------------------------------------------------

def berger_rounds(n: int) -> list[list[tuple[int, int]]]:
    """
    Rounds of a round robin by the Berger tables: a list of rounds, a round is pairs (white, black) of numbers 1..n.
    The last number "stays in place", the rest rotate; colours as in the FIDE tables.
    """
    if n not in ROUND_ROBIN_SIZES:
        raise ValueError(f"round robin needs {ROUND_ROBIN_SIZES} players, got {n}")
    return _berger(n)


def _berger(n: int) -> list[list[tuple[int, int]]]:
    """A Berger table for any even n: the rotation step n/2 is coprime with n - 1, so everybody meets."""
    m = n - 1

    def cyc(x: int) -> int:
        return (x - 1) % m + 1

    rounds = []
    for r in range(m):
        fixed = (r * (n // 2)) % m + 1
        pairs = [(fixed, n) if r % 2 == 0 else (n, fixed)]
        pairs += [(cyc(fixed + k), cyc(fixed - k)) for k in range(1, n // 2)]
        rounds.append(pairs)
    return rounds


def round_robin_schedule(n: int, cycles: int = 1) -> list[list[tuple[int, int]]]:
    """
    Schedule of a round robin for any number of participants and circuits. With odd n the table is built for n + 1:
    whoever gets the non-existent number sits out that round. Each next circuit repeats the pairs with colours swapped.
    """
    if n not in OPEN_ROUND_ROBIN_SIZES:
        raise ValueError(f"round robin needs {OPEN_ROUND_ROBIN_SIZES.start}–{OPEN_ROUND_ROBIN_SIZES[-1]} players, got {n}")
    if not 1 <= cycles <= MAX_CYCLES:
        raise ValueError(f"round robin has 1–{MAX_CYCLES} cycles, got {cycles}")
    table = _berger(n + n % 2)
    single = [[pair for pair in rnd if max(pair) <= n] for rnd in table]
    rounds = []
    for cycle in range(cycles):
        rounds += single if cycle % 2 == 0 else [[(black, white) for white, black in rnd] for rnd in single]
    return rounds


@dataclass(frozen=True)
class GameRecord:
    """A played game for computing tables: the numbers of the participants as White and Black, and the result."""
    white: int
    black: int
    result: Result


@dataclass(frozen=True)
class Standing:
    """A row of the final table: points, tie-break indicators and the place (1 is the best)."""
    seat: int
    points: float
    # Points in games among those tied (round robin only; in the Swiss always 0).
    head_to_head: float
    sonneborn_berger: float
    place: int
    # Buchholz - the sum of the opponents' points (Swiss system).
    buchholz: float = 0.0


def _score(game: GameRecord, seat: int) -> float:
    """Points of participant seat for a game: 1, 0.5 or 0."""
    if game.result == "1/2-1/2":
        return 0.5
    won_white = game.result == "1-0"
    return 1.0 if (seat == game.white) == won_white else 0.0


def round_robin_standings(seats: list[int], games: list[GameRecord]) -> list[Standing]:
    """Round robin table by played games, places taking the tie-breaks into account."""
    points = {s: 0.0 for s in seats}
    for g in games:
        points[g.white] += _score(g, g.white)
        points[g.black] += _score(g, g.black)

    sb = {s: 0.0 for s in seats}
    for g in games:
        for seat, opponent in ((g.white, g.black), (g.black, g.white)):
            sb[seat] += _score(g, seat) * points[opponent]

    h2h = {s: 0.0 for s in seats}
    for s in seats:
        tied = {o for o in seats if points[o] == points[s]}
        h2h[s] = sum(_score(g, s) for g in games if s in (g.white, g.black) and {g.white, g.black} <= tied)

    order = sorted(seats, key=lambda s: (-points[s], -h2h[s], -sb[s], s))
    return [
        Standing(seat=s, points=points[s], head_to_head=h2h[s], sonneborn_berger=sb[s], place=i + 1)
        for i, s in enumerate(order)
    ]


# --- Swiss system ----------------------------------------------------------------------------

def _points(seats: list[int], games: list[GameRecord]) -> dict[int, float]:
    """The sum of each participant's points over the played games."""
    points = {s: 0.0 for s in seats}
    for g in games:
        points[g.white] += _score(g, g.white)
        points[g.black] += _score(g, g.black)
    return points


def swiss_standings(seats: list[int], games: list[GameRecord]) -> list[Standing]:
    """Swiss table: points, then Buchholz (the sum of opponents' points), Sonneborn-Berger, seeding."""
    points = _points(seats, games)
    buchholz = {s: 0.0 for s in seats}
    sb = {s: 0.0 for s in seats}
    for g in games:
        for seat, opponent in ((g.white, g.black), (g.black, g.white)):
            buchholz[seat] += points[opponent]
            sb[seat] += _score(g, seat) * points[opponent]
    order = sorted(seats, key=lambda s: (-points[s], -buchholz[s], -sb[s], s))
    return [
        Standing(seat=s, points=points[s], head_to_head=0.0, sonneborn_berger=sb[s], place=i + 1, buchholz=buchholz[s])
        for i, s in enumerate(order)
    ]


def _colors(a: int, b: int, games: list[GameRecord]) -> tuple[int, int]:
    """White goes to whoever has fewer whites (whites minus blacks); on a tie - whoever played Black last game,
    then the higher seed."""
    def balance(seat: int) -> int:
        return sum(1 if g.white == seat else -1 for g in games if seat in (g.white, g.black))

    def last_white(seat: int) -> bool | None:
        own = [g for g in games if seat in (g.white, g.black)]
        return own[-1].white == seat if own else None

    if balance(a) != balance(b):
        return (a, b) if balance(a) < balance(b) else (b, a)
    if last_white(a) is not None and last_white(a) != last_white(b):
        return (b, a) if last_white(a) else (a, b)
    return (a, b) if a < b else (b, a)


def swiss_pairings(seats: list[int], games: list[GameRecord]) -> list[tuple[int, int]]:
    """
    Pairs of the next round (white, black). The first round - the upper half of the seeding against the lower (1-4, 2-5,
    3-6), colours alternate by board. Then by points: each, starting from the leader, gets the nearest opponent in the
    table they have not played yet (backtracking guarantees that pairs are found for everybody); if it is impossible
    without repeats - a repeat is allowed.
    """
    ordered = sorted(seats)
    if not games:
        half = len(ordered) // 2
        pairs = []
        for board, (high, low) in enumerate(zip(ordered[:half], ordered[half:], strict=True)):
            pairs.append((high, low) if board % 2 == 0 else (low, high))
        return pairs
    points = _points(seats, games)
    ranking = sorted(seats, key=lambda s: (-points[s], s))
    played = {frozenset((g.white, g.black)) for g in games}

    def search(rest: list[int], allow_repeat: bool) -> list[tuple[int, int]] | None:
        """
        Backtracking: splits the participants into pairs. allow_repeat allows repeat meetings - when pairs
        cannot be made without them.
        """
        if not rest:
            return []
        first = rest[0]
        for opponent in rest[1:]:
            if not allow_repeat and frozenset((first, opponent)) in played:
                continue
            tail = search([s for s in rest[1:] if s != opponent], allow_repeat)
            if tail is not None:
                return [(first, opponent), *tail]
        return None

    found = search(ranking, False) or search(ranking, True)
    assert found is not None
    return [_colors(a, b, games) for a, b in found]


# --- Knockout ------------------------------------------------------------------------------------

def knockout_first_round(n: int) -> list[tuple[int, int]]:
    """Pairs of the first round by seeding (the higher seed first)."""
    if n == 4:
        return [(1, 4), (2, 3)]
    if n == 8:
        return [(1, 8), (4, 5), (2, 7), (3, 6)]
    raise ValueError(f"knockout needs {KNOCKOUT_SIZES} players, got {n}")


def bracket_size(n: int) -> int:
    """Bracket size: the nearest power of two not less than the number of participants."""
    size = 2
    while size < n:
        size *= 2
    return size


def bracket_slots(n: int) -> list[tuple[int, int | None]]:
    """
    The first round of a bracket for any number of participants: pairs (higher seed, opponent) in bracket order. No opponent
    (None) - the participant passes the round without playing; this is how the strongest seeds pass. The bracket is
    classic: the first and second numbers meet only in the final, for 4 and 8 it coincides with knockout_first_round.
    """
    if n not in OPEN_KNOCKOUT_SIZES:
        raise ValueError(f"knockout needs {OPEN_KNOCKOUT_SIZES.start}–{OPEN_KNOCKOUT_SIZES[-1]} players, got {n}")
    order = [1, 2]
    while len(order) < bracket_size(n):
        full = len(order) * 2
        order = [seat for high in order for seat in (high, full + 1 - high)]
    return [(high, low if low <= n else None) for high, low in zip(order[::2], order[1::2], strict=True)]


@dataclass(frozen=True)
class MatchGame:
    """A knockout match game: stage, the numbers of the players as White and Black, and the shortened-control flag."""
    stage: Stage
    white: int
    black: int
    shortened: bool


def match_game(high: int, low: int, stage: Stage) -> MatchGame:
    """Colours and control of a match game: high - the higher seed."""
    if stage == "main":
        return MatchGame("main", white=high, black=low, shortened=False)
    if stage == "rematch":
        return MatchGame("rematch", white=low, black=high, shortened=True)
    return MatchGame("armageddon", white=low, black=high, shortened=True)


def shortened_control(base_ms: int, increment_ms: int) -> tuple[int, int]:
    """Control of a replay and a deciding game: half as long, but not less than a minute."""
    return max(MIN_SHORTENED_BASE_MS, base_ms // 2), increment_ms // 2


@dataclass(frozen=True)
class MatchState:
    """Match state: the winner (if determined) or the next game."""
    winner: int | None
    next_game: MatchGame | None


def match_state(high: int, low: int, played: list[tuple[Stage, GameRecord]]) -> MatchState:
    """
    Match result by the played games (in order of play): the winner or the next game.
    In the deciding game a draw is a Black win.
    """
    stages: list[Stage] = ["main", "rematch", "armageddon"]
    for stage, game in played:
        if game.result == "1-0":
            return MatchState(game.white, None)
        if game.result == "0-1":
            return MatchState(game.black, None)
        if stage == "armageddon":
            return MatchState(game.black, None)
    next_stage = stages[len(played)]
    return MatchState(None, match_game(high, low, next_stage))


def knockout_next_round(winners: list[int]) -> list[tuple[int, int]]:
    """Pairs of the next round: winners of neighbouring bracket matches; the higher seed first."""
    return [(min(a, b), max(a, b)) for a, b in zip(winners[::2], winners[1::2], strict=True)]


def knockout_places(n: int, eliminated_in_round: dict[int, int], champion: int) -> dict[int, int]:
    """
    Places: the winner is 1, the loser of the final 2, the semi-final losers share 3rd, the quarter-final losers 5th,
    those out a round earlier 9th and so on. eliminated_in_round: participant number -> round (from 1) in which they were
    eliminated.
    """
    rounds_total = bracket_size(n).bit_length() - 1
    places = {champion: 1}
    for seat, rnd in eliminated_in_round.items():
        from_end = rounds_total - rnd  # 0 - final, 1 - semi-final, 2 - quarter-final
        places[seat] = 2 if from_end == 0 else 2 ** from_end + 1
    return places
