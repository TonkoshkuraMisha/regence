# --- FILE: src/services/onboarding.py ---
"""
First login (task 17.8): two optional questions at registration - how long you have been playing and approximate strength -
give the starting rating. Opponents and puzzles are selected by it from the first game; while there are fewer games in a
category than PROVISIONAL_GAMES, the rating is provisional (K = 40 and a mark in the interface) and quickly catches up with
the real strength.

Without answers - the former 1200. "Just learned the rules" is the lowest start, strength is then not asked.

Who applies it: registration (src/api/auth.py) writes the starting value at once to all game rating categories
and to the puzzle rating (the users.*_rating columns). Without answers the model defaults apply: games - 1200,
puzzles - 1500. PROVISIONAL_GAMES is a constant of src/services/rating.py.
"""

from typing import Literal

Experience = Literal["new", "casual", "regular"]
StrengthBand = Literal["under_1000", "1000_1400", "1400_1800", "over_1800"]

DEFAULT_RATING = 1200  # no answers, or "play regularly" without strength; the User model default
BEGINNER_RATING = 600  # "just learned the rules"
# Range midpoints, adjusted downward for the top two (1550 instead of 1600): the claimed strength is usually higher than
# the real one.
BAND_RATINGS: dict[str, int] = {"under_1000": 800, "1000_1400": 1200, "1400_1800": 1550, "over_1800": 1850}
# Without a strength estimate: "play occasionally" - a little below the middle of the scale, "play regularly" - the middle.
EXPERIENCE_RATINGS: dict[str, int] = {"casual": 1000, "regular": DEFAULT_RATING}


def starting_rating(experience: Experience | None, strength: StrengthBand | None) -> int:
    """
    Starting rating from the answers, in descending priority: a beginner - BEGINNER_RATING (strength is not taken into
    account); strength given - BAND_RATINGS; only experience given - EXPERIENCE_RATINGS; otherwise DEFAULT_RATING.
    """
    if experience == "new":
        return BEGINNER_RATING
    if strength is not None:
        return BAND_RATINGS[strength]
    if experience is not None:
        return EXPERIENCE_RATINGS[experience]
    return DEFAULT_RATING
