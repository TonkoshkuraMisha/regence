# --- FILE: src/services/game_summary.py ---
"""
Game summary (task 11.5): the game type by the evaluation graph and key moments -- from the already finished analysis,
without an engine.

Types (checked in order, the first match wins):
* ``seesaw`` -- "seesaw": a decisive advantage (>= LEAD_CP) passed from one side to the other at least twice;
* ``decisive_blunder`` -- "decided by a mistake": the loser blundered badly without having been behind before, and after the
  mistake
  the advantage never returned to them;
* ``domination`` -- "domination": the winner was never noticeably worse and was better for almost the whole game;
* ``missed_win`` -- "missed win": a draw although one of the sides had a winning advantage (>= WINNING_CP);
* ``balanced`` -- "even fight": the position was equal for more than EQUAL_SHARE of the moves (|evaluation| < EQUAL_CP);
* ``gradual`` -- "gradual advantage": everything else -- the advantage built up without a single turning point.

Evaluations are from White's point of view, mate is clamped to +-CLAMP_CP. Each side's key moments: the best move (an
accurate move with
the biggest evaluation improvement in its favour over a couple of plies -- this also counts punishing the opponent's mistake)
and
the worst (the biggest loss).

Where the data comes from: the move list of the finished analysis (the "moves" field of games.analysis_json or of the
imported game's analysis --
each move has the evaluation after it eval_cp, the loss cp_loss, the colour and the ply number) and the game result. The
summary
is not stored: it is computed on every analysis delivery (src/api/analysis.py, src/api/game_import.py).
"""

from collections.abc import Sequence

# All thresholds are in centipawns, the evaluation from White's point of view.
LEAD_CP = 150           # a side's advantage: the evaluation is at least this in its favour
WINNING_CP = 300        # a winning advantage (for "missed win")
EQUAL_CP = 100          # the position is equal: the evaluation modulus is below this
EQUAL_SHARE = 0.4       # "even fight": equal positions make up more than this share of the game
DOMINATION_SHARE = 0.7  # "domination": the winner was better in at least this share of positions after the opening
BLUNDER_CP = 200        # the move loss from which it counts as a decisive mistake
CLAMP_CP = 1000         # evaluations (including mate) are clamped to +-this value
OPENING_PLIES = 8       # this many first plies are excluded from the "was better" share for "domination"
# A missed shot (task B.5): the opponent erred by at least MISSED_ERROR_CP, and the reply lost at least
# MISSED_REPLY_CP of it -- it was possible to punish but they did not. The list holds at most MAX_MISSED.
MISSED_ERROR_CP = 150
MISSED_REPLY_CP = 150
MAX_MISSED = 5


def _clamp(value: int) -> int:
    return max(-CLAMP_CP, min(CLAMP_CP, value))


def _winner(result: str | None) -> int:
    """+1 -- White won, -1 -- Black, 0 -- a draw or a game without a result."""
    return {"1-0": 1, "0-1": -1}.get(result or "", 0)


def _leader(eval_cp: int) -> int:
    """Who has the advantage at this evaluation: +1 -- White, -1 -- Black, 0 -- nobody (below LEAD_CP)."""
    if eval_cp >= LEAD_CP:
        return 1
    if eval_cp <= -LEAD_CP:
        return -1
    return 0


def _lead_changes(evals: Sequence[int]) -> int:
    """
    How many times the advantage passed from one side to the other; equal positions between them do not cancel the
    transition.
    """
    changes = 0
    last = 0
    for value in evals:
        leader = _leader(value)
        if leader == 0:
            continue
        if last and leader != last:
            changes += 1
        last = leader
    return changes


def _turning_point(moves: Sequence[dict], evals: Sequence[int], winner: int) -> int | None:
    """
    A gross mistake by the loser after which the winner's advantage never left: the ply number or None. Conditions:
    the move loss is at least BLUNDER_CP, before it the winner did not have even half of LEAD_CP, and after it until the end of
    the game the winner's advantage did not drop below LEAD_CP.
    """
    loser_color = "black" if winner == 1 else "white"
    previous = 0
    for index, move in enumerate(moves):
        before = previous
        previous = evals[index]
        if move.get("color") != loser_color or int(move.get("cp_loss", 0)) < BLUNDER_CP:
            continue
        # Before the mistake the loser was not worse, after it the game is lost and the advantage never returned.
        if before * winner > LEAD_CP / 2:
            continue
        if all(value * winner >= LEAD_CP for value in evals[index:]):
            return int(move.get("ply", index + 1))
    return None


def _key_moments(moves: Sequence[dict], evals: Sequence[int], color: str) -> dict:
    """
    A side's best and worst moves (ply numbers or None). The best is a move with a loss of at most 10 and the biggest
    evaluation improvement over a couple of plies, if the improvement is at least 50; the worst is the move with the biggest
    loss, if it is
    at least 50.
    """
    sign = 1 if color == "white" else -1
    best_ply: int | None = None
    best_gain = 0
    worst_ply: int | None = None
    worst_loss = 0
    for index, move in enumerate(moves):
        if move.get("color") != color:
            continue
        loss = int(move.get("cp_loss", 0))
        # The gain is counted from the position before the opponent's move: the move that punished their mistake is also a
        # best moment.
        baseline = evals[index - 2] if index >= 2 else 0
        gain = (evals[index] - baseline) * sign
        if loss <= 10 and gain > best_gain:
            best_gain, best_ply = gain, int(move.get("ply", index + 1))
        if loss > worst_loss:
            worst_loss, worst_ply = loss, int(move.get("ply", index + 1))
    # A "best move" without a noticeable gain and a "worst" without a noticeable loss are not moments.
    return {
        "best_ply": best_ply if best_gain >= 50 else None,
        "worst_ply": worst_ply if worst_loss >= 50 else None,
    }


def _missed_punishments(moves: Sequence[dict]) -> list[dict]:
    """Plies where a side did not punish the opponent's big mistake -- the most costly first."""
    missed: list[dict] = []
    for previous, move in zip(moves, moves[1:], strict=False):
        if previous.get("color") == move.get("color"):
            continue
        if int(previous.get("cp_loss", 0)) >= MISSED_ERROR_CP and int(move.get("cp_loss", 0)) >= MISSED_REPLY_CP:
            missed.append({"ply": int(move.get("ply", 0)), "color": move.get("color"), "cp": int(move.get("cp_loss", 0))})
    missed.sort(key=lambda item: -int(item["cp"]))
    return sorted(missed[:MAX_MISSED], key=lambda item: item["ply"])


def summarize(moves: Sequence[dict], result: str | None) -> dict | None:
    """
    A summary by the analysis moves (moves from analysis_json) and the game result. An empty game -- None. Returns the game
    type
    (kind), the ply of the decisive mistake, the number of advantage transitions, the share of equal positions, the sides'
    key moments and
    the missed shots. A game without a winner (draw, interrupted) has no decisive mistake and no "domination".
    """
    if not moves:
        return None
    evals = [_clamp(int(move.get("eval_cp", 0))) for move in moves]
    winner = _winner(result)
    middlegame = evals[OPENING_PLIES:] or evals
    equal_share = sum(1 for value in evals if abs(value) < EQUAL_CP) / len(evals)
    changes = _lead_changes(evals)
    turning_point = _turning_point(moves, evals, winner) if winner else None

    kind: str
    if changes >= 2:
        kind = "seesaw"
    elif turning_point is not None:
        kind = "decisive_blunder"
    elif winner and all(value * winner > -LEAD_CP for value in evals) and (
            sum(1 for value in middlegame if value * winner > 0) / len(middlegame) >= DOMINATION_SHARE):
        kind = "domination"
    elif not winner and any(abs(value) >= WINNING_CP for value in evals):
        kind = "missed_win"
    elif equal_share > EQUAL_SHARE:
        kind = "balanced"
    else:
        kind = "gradual"

    return {
        "kind": kind,
        "turning_point_ply": turning_point,
        "lead_changes": changes,
        "equal_share": round(equal_share, 3),
        "white": _key_moments(moves, evals, "white"),
        "black": _key_moments(moves, evals, "black"),
        "missed": _missed_punishments(moves),
    }
