"""
Elo rating and time-control categories.

A game's category is by the estimate of its duration "base + 40 x increment": under 3 minutes - bullet, under 8 - blitz,
under 25 - rapid, otherwise classical (classify_time_control). A player has a separate rating and game counter in each
category (users.*_rating, users.*_games_played).

Recalculation after a game (FideEloSystem.calculate_new_ratings): the expected result from the rating difference, the change
= K x (result - expectation). K = 40 for the first PROVISIONAL_GAMES games in a category ("provisional" rating), then 20,
from 2400 - 10. The rating does not fall below 100. Called when a rated game finishes
(src/services/game_state.finish_game); the change is saved in games.*_rating_delta.

K is different for each player, so the changes of the two sides need not be equal in size. The puzzle solver's rating
is computed separately (src/services/puzzles.rating_delta), the ladder and bot ratings - in their own modules.
"""

from src.models.user import RatingCategory

# Category by the estimate of a game's duration (base + 40 moves for the per-move increment) - the same
# heuristic that lichess.org uses to separate bullet/blitz/rapid/classical.
# Each constant is the lower bound of the named category in seconds: from 3 minutes - blitz, from 8 - rapid, from 25 -
# classical; under 3 minutes - bullet.
_BLITZ_THRESHOLD_S = 180
_RAPID_THRESHOLD_S = 480
_CLASSICAL_THRESHOLD_S = 1500
# How many moves are built into the game duration estimate.
ESTIMATED_MOVES = 40
# For the first games in a category the rating is provisional: K = 40 and a mark in the interface (task 17.8).
PROVISIONAL_GAMES = 30


def classify_time_control(base_time_ms: int, increment_ms: int) -> RatingCategory:
    """Time-control category by the estimate of the game's duration (the boundaries are in the module description)."""
    estimated_s = base_time_ms / 1000 + ESTIMATED_MOVES * (increment_ms / 1000)
    if estimated_s < _BLITZ_THRESHOLD_S:
        return "bullet"
    if estimated_s < _RAPID_THRESHOLD_S:
        return "blitz"
    if estimated_s < _CLASSICAL_THRESHOLD_S:
        return "rapid"
    return "classical"


def category_duration_bounds_ms(category: RatingCategory) -> tuple[int | None, int | None]:
    """
    Category bounds [lower, upper) by the duration estimate base_time_ms + 40 * increment_ms.
    Needed to select a category's games in SQL by the same rule as classify_time_control.
    """
    thresholds_ms = [_BLITZ_THRESHOLD_S * 1000, _RAPID_THRESHOLD_S * 1000, _CLASSICAL_THRESHOLD_S * 1000]
    lower = [None, *thresholds_ms]
    upper = [*thresholds_ms, None]
    index = ("bullet", "blitz", "rapid", "classical").index(category)
    return lower[index], upper[index]


class FideEloSystem:
    """
    Rating calculation system according to FIDE standards.
    Includes a dynamic K-factor depending on the current rating and experience.

    Simplifications compared with the FIDE rules: K = 10 applies while the current rating is not below 2400 (not forever
    after reaching it); there is no special K for young players; recalculation is after every game.
    """

    @staticmethod
    def get_k_factor(rating: int, games_played: int = PROVISIONAL_GAMES) -> int:
        """
        K-factor: 40 - while fewer than PROVISIONAL_GAMES games have been played in the category (at any rating), then 10 at
        a rating from 2400 and 20 otherwise. games_played is the number of games before this game.
        """
        if games_played < PROVISIONAL_GAMES:
            return 40
        if rating >= 2400:
            return 10
        return 20

    @staticmethod
    def expected_score(rating_a: int, rating_b: int) -> float:
        """Expected result of player A against B (from 0 to 1) by the logistic Elo formula: 400 points - 10 to 1."""
        return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))

    @classmethod
    def calculate_new_ratings(
        cls,
        white_rating: int,
        black_rating: int,
        result: str,
        white_games: int = 30,
        black_games: int = 30
    ) -> tuple[int, int, int, int]:
        """
        Returns: (new_white_rating, white_delta, new_black_rating, black_delta)

        result - "1-0", "0-1", "1/2-1/2" or the codes white_won_on_time, black_won_on_time, draw_agreement; any other
        value is a ValueError. white_games and black_games are the player's number of games in the category before this
        game (by default 30, i.e. the rating is no longer provisional). The delta returned is the computed one: if the
        rating hit the lower bound of 100, the actual change is smaller than the returned delta.
        """
        if result in ("1-0", "white_won_on_time"):
            score_white, score_black = 1.0, 0.0
        elif result in ("0-1", "black_won_on_time"):
            score_white, score_black = 0.0, 1.0
        elif result in ("1/2-1/2", "draw_agreement"):
            score_white, score_black = 0.5, 0.5
        else:
            raise ValueError(f"Unknown game result: {result}")

        expected_white = cls.expected_score(white_rating, black_rating)
        expected_black = cls.expected_score(black_rating, white_rating)

        k_white = cls.get_k_factor(white_rating, white_games)
        k_black = cls.get_k_factor(black_rating, black_games)

        delta_white = round(k_white * (score_white - expected_white))
        delta_black = round(k_black * (score_black - expected_black))

        # Protection against the rating falling below 100
        new_white = max(100, white_rating + delta_white)
        new_black = max(100, black_rating + delta_black)

        return new_white, delta_white, new_black, delta_black


elo_calculator = FideEloSystem()
