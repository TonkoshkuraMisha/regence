# --- FILE: src/services/anticheat.py ---
"""
Anti-cheat from move telemetry: after a game it evaluates the rhythm of play and changes the player's trust factor.

Data source: table moves — time per move by the server clock, window focus loss and premoves (from the client).
The main signal is an even "machine" rhythm: average move time from 1.5 to 15 seconds with a small spread (coefficient
of variation up to 0.12 — penalty 40, up to 0.22 — 22). Window focus loss is reported by the client and can be forged, so on
its own
it does not penalise, but only strengthens the penalty when the rhythm already looks like an engine: a share of moves with
focus loss from
0.35 — another 12, from 0.50 — 25, from 0.75 — 45, and another 15 if the share is from 0.65 with variation up to 0.20. A
premove is excluded
from the rhythm only if the server itself sees an almost instant move (trusted_premove).

The rhythm and focus thresholds are written as numbers in compute_telemetry_penalty; only AC_PREMOVE_MAX_ELAPSED_MS is
read from the settings (src/core/config.py).

Result: the penalty is subtracted from users.trust_factor (starts at 100); below CHEATER_TRUST_THRESHOLD the flag
is_cheater is set and a report to the moderator is created (src/services/moderation.py) — a human makes the decision. A game
is evaluated once (a marker in Redis, key anticheat:evaluated:{game_id}). Engine requests from the player's address during a
game are only recorded as a signal for review — there is no penalty for them. Called when a game finishes
(src/services/game_state.py). Also there the per-side rhythm summary is written to games.telemetry_summary (telemetry_summary):
the raw moves are kept only RETENTION_DAYS (src/services/telemetry_retention.py).
"""

import logging
import math

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.game import Game
from src.models.move import Move
from src.models.user import User

logger = logging.getLogger(__name__)

# Fewer than this many player moves in a game — the rhythm is not evaluated, no penalty.
MIN_MOVES_FOR_ANALYSIS = 5
# The share of moves with focus loss is computed over moves after this move number (the first moves of the game are not
# counted).
OPENING_MOVE_CUTOFF = 8
# Trust factor below this value — the is_cheater flag and a report to the moderator.
CHEATER_TRUST_THRESHOLD = 30
# Lifetime of the "game already evaluated" marker in Redis (90 days): within this period repeated evaluation does not penalise.
EVALUATED_MARKER_TTL_S = 90 * 24 * 60 * 60


def trusted_premove(client_flag, server_elapsed_ms: int) -> bool:
    """
    A premove excludes a move from the rhythm analysis, so the client flag is accepted only if the server
    itself sees an almost instant move (no longer than settings.AC_PREMOVE_MAX_ELAPSED_MS, 600 ms by default). Otherwise a
    cheater
    could mark all moves as premoves.
    """
    from src.core.config import settings

    return bool(client_flag) and int(server_elapsed_ms) <= settings.AC_PREMOVE_MAX_ELAPSED_MS


async def _claim_first_evaluation(game_id: int) -> bool:
    """
    True if the game is evaluated for the first time. The marker is stored in Redis (SET NX), not in the memory of the
    process: after a restart or on another worker the penalty for the same game will not be applied again. The key is
    anticheat:evaluated:{game_id}, the lifetime is EVALUATED_MARKER_TTL_S. Redis unavailable — False: the game is considered
    already
    evaluated and no penalty is applied.
    """
    from src.db import redis as redis_module

    try:
        claimed = await redis_module.redis_client.set(
            f"anticheat:evaluated:{int(game_id)}", "1", nx=True, ex=EVALUATED_MARKER_TTL_S,
        )
        return bool(claimed)
    except Exception as exc:
        logger.warning("Anti-cheat idempotency marker unavailable for game %s: %s", game_id, exc)
        return False  # without a marker we do not penalise: a repeated penalty is worse than a missed one


def calculate_blur_ratio(moves: list[Move]) -> float:
    """
    Computes the share of moves with window focus loss (window_blurred_before_move == True)
    after the 8th move. If there are fewer than 3 moves after the 8th move, all of the player's moves are evaluated.
    """
    if not moves:
        return 0.0

    post_opening = [m for m in moves if (m.move_number or 0) > OPENING_MOVE_CUTOFF]
    target_moves = post_opening if len(post_opening) >= 3 else moves

    blurred_count = sum(1 for m in target_moves if bool(m.window_blurred_before_move))
    return round(blurred_count / len(target_moves), 4)


def calculate_timing_cv(moves: list[Move]) -> tuple[float, float]:
    """
    Computes the coefficient of variation of move times (CV = std_dev / mean),
    excluding premoves (is_premove == True) and moves without a recorded time. Returns (cv, mean_time_ms).
    If there are fewer than three such moves — (1.0, 0.0): no penalty is applied for these values.
    """
    normal_times = [
        float(m.time_taken_ms)
        for m in moves
        if not bool(m.is_premove) and (m.time_taken_ms or 0) > 0
    ]

    if len(normal_times) < 3:
        return 1.0, 0.0

    # The times are filtered by > 0, so the mean is strictly positive and the division is safe.
    mean_time = sum(normal_times) / len(normal_times)
    variance = sum((t - mean_time) ** 2 for t in normal_times) / len(normal_times)
    std_dev = math.sqrt(variance)
    return round(std_dev / mean_time, 4), round(mean_time, 1)


def compute_telemetry_penalty(moves: list[Move]) -> dict:
    """
    Computes the trust-factor penalty from the Tab-Switch and Timing Variance patterns for one player's moves in one
    game. Returns the penalty and the measured values (share of moves with focus loss, variation and average move time).
    Fewer than MIN_MOVES_FOR_ANALYSIS moves — penalty 0. The largest possible penalty per game is 40 + 45 + 15 = 100.
    """
    if len(moves) < MIN_MOVES_FOR_ANALYSIS:
        return {
            "penalty": 0,
            "blur_ratio": 0.0,
            "timing_cv": 1.0,
            "mean_time_ms": 0.0,
        }

    blur_ratio = calculate_blur_ratio(moves)
    timing_cv, mean_time_ms = calculate_timing_cv(moves)

    # The main signal is the move rhythm measured by the server (time_taken_ms is the server time
    # between moves). Window focus loss is reported by the client and can be forged in both directions,
    # so on its own it does not penalise (otherwise honest players with a second monitor suffer)
    # and only strengthens the penalty when the server rhythm already looks like an engine.
    timing_penalty = 0
    is_engine_pacing = 1500.0 <= mean_time_ms <= 15000.0
    if is_engine_pacing:
        if timing_cv <= 0.12:
            timing_penalty = 40
        elif timing_cv <= 0.22:
            timing_penalty = 22

    blur_penalty = 0
    if timing_penalty > 0:
        if blur_ratio >= 0.75:
            blur_penalty = 45
        elif blur_ratio >= 0.50:
            blur_penalty = 25
        elif blur_ratio >= 0.35:
            blur_penalty = 12
        if blur_ratio >= 0.65 and timing_cv <= 0.20:
            blur_penalty += 15

    penalty = timing_penalty + blur_penalty

    return {
        "penalty": penalty,
        "blur_ratio": blur_ratio,
        "timing_cv": timing_cv,
        "mean_time_ms": mean_time_ms,
    }


def telemetry_summary(game: Game, moves: list[Move]) -> dict[str, dict]:
    """
    Telemetry summary of a game by side ({"white": ..., "black": ...}) — what remains in games.telemetry_summary
    after the raw moves are deleted (src/services/telemetry_retention.py): number of moves and premoves, the largest network
    delay and the compute_telemetry_penalty values (penalty, focus-loss share, variation and average move time).
    """
    summary: dict[str, dict] = {}
    for color, player_id in (("white", game.white_player_id), ("black", game.black_player_id)):
        own = [m for m in moves if m.player_id == player_id]
        summary[color] = {
            "moves": len(own),
            "premoves": sum(1 for m in own if m.is_premove),
            "max_lag_ms": max((int(m.network_lag_ms or 0) for m in own), default=0),
            **compute_telemetry_penalty(own),
        }
    return summary


async def evaluate_game_telemetry(db: AsyncSession, game_id: int, force: bool = False) -> dict[int, dict]:
    """
    Analyses the telemetry of a finished game for both players,
    lowers user.trust_factor on anomalies and sets is_cheater = True when trust_factor < 30.
    Idempotent by game_id (a repeated call for the same game does not penalise the player twice); force=True skips
    the marker check and penalises again. Moves are taken from the moves table. Returns for each player the measured
    values, the number of engine requests from their address during the game, the trust factor and the flag; no game or no
    moves — {}.
    """
    from src.api.fair_play import engine_requests_during_game

    game = await db.get(Game, game_id)
    if not game:
        return {}

    result = await db.execute(
        select(Move).where(Move.game_id == game_id).order_by(Move.id.asc())
    )
    all_moves = list(result.scalars().all())
    if not all_moves:
        return {}

    already_evaluated = not force and not await _claim_first_evaluation(game_id)
    # The summary goes first: the raw moves will be deleted by the retention task after RETENTION_DAYS, while the summary stays
    # with the game.
    game.telemetry_summary = telemetry_summary(game, all_moves)

    moves_by_player: dict[int, list[Move]] = {
        game.white_player_id: [],
        game.black_player_id: [],
    }
    for move in all_moves:
        moves_by_player.setdefault(move.player_id, []).append(move)

    report: dict[int, dict] = {}

    for player_id, player_moves in moves_by_player.items():
        metrics = compute_telemetry_penalty(player_moves)
        penalty = 0 if already_evaluated else metrics["penalty"]

        user = await db.get(User, player_id)
        if not user:
            continue

        if penalty > 0:
            user.trust_factor = max(0, int(user.trust_factor) - penalty)
            if user.trust_factor < CHEATER_TRUST_THRESHOLD:
                if not user.is_cheater:
                    # The flag is set automatically, but a moderator reviews the decision (task 17.4): a report goes to the
                    # queue.
                    from src.services.moderation import flag_for_review
                    await flag_for_review(db, user, game_id)
                user.is_cheater = True
                logger.warning(
                    "Fair Play Alert: user %s (id=%s) flagged in game %s (trust_factor=%s, blur=%.2f, cv=%.2f)",
                    user.username,
                    user.id,
                    game_id,
                    user.trust_factor,
                    metrics["blur_ratio"],
                    metrics["timing_cv"],
                )

        # Engine requests by another account from the player's address during the game: only a signal for
        # review — different people may share a network, so there is no penalty for it.
        engine_requests = await engine_requests_during_game(game_id, player_id)
        if engine_requests and not already_evaluated:
            logger.warning(
                "Fair Play signal: %s engine request(s) from the address of user %s (id=%s) during game %s",
                engine_requests, user.username, user.id, game_id,
            )

        report[player_id] = {
            **metrics,
            "engine_requests_same_ip": engine_requests,
            "trust_factor": user.trust_factor,
            "is_cheater": user.is_cheater,
        }

    await db.commit()
    return report
