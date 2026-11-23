# --- FILE: src/services/defense_drills.py ---
"""
Defence exercises (task 13.6) -- section I of the theme catalogue: "What does the opponent threaten?" (find_the_threat) and
"Don't blunder"
(blunder_check). "Only defence" (defensive_move) consists of ordinary database puzzles tagged lichess, served by the
motif training (13.4).

Where positions come from. A lichess puzzle is the losing side's mistake (moves[0]) and the winner's tactic (moves[1]).
It yields two exercises "for the defender":

* "What does the opponent threaten?" -- the position after the mistake, but with the move passed back to the side that erred
  (a null move by the opponent): the opponent's
  tactic becomes a threat. The player first shows the threat (the attacking piece or the target square), then
  defends. A correct defence is any move the engine rates almost as the best (``GOOD_MARGIN``).
* "Don't blunder" -- the position before the mistake and three natural moves: the blunder played by the human, another losing
  move
  that "looks good by eye" (a high shallow-search score), and the one safe move. For the losing
  moves a refutation is stored -- the opponent's reply.

The solvability criteria (``threat_drill`` / ``blunder_drill``, then independently ``verify_drill``) are checked by the engine
when the sample is built offline
(scripts/dev/build_defense_drills.py -> data/puzzles/defense_drills.csv.gz); the server does not run the engine for the
exercises.
Progress is by the themes find_the_threat / blunder_check, the exercise stage by the rating of the source puzzle.

Where it is stored: exercises -- the defense_drills table (loaded from the sample file, import_drills); progress --
theme_progress; the exercise the player is solving now -- Redis defense:session:{user_id} (lives SESSION_TTL_S),
recently served ones -- the list defense:recent:{user_id}. The correct moves, the threat and the refutations are not sent to
the client before the
answer (public_view).
"""

import csv
import gzip
import json
import pathlib
import random
from collections.abc import Callable, Iterable, Iterator
from dataclasses import asdict, dataclass

import chess
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DomainValueError
from src.db import redis as redis_module
from src.models.puzzle import DefenseDrill, ThemeProgress
from src.models.user import User
from src.services.puzzles import PuzzleError, reset_stage_counts, update_theme_progress

# The sample file and its columns. Threat -- the opponent's threat move (UCI); Choices -- the three "Don't blunder" moves
# separated by spaces;
# Refutations -- "move:opponent's reply" pairs for the losing moves; Good -- correct moves separated by spaces; Motifs -- motif
# codes separated by spaces. SourceId -- the id of the source lichess puzzle.
DRILLS_FILE = pathlib.Path(__file__).resolve().parents[2] / "data" / "puzzles" / "defense_drills.csv.gz"
FIELDS = ("Kind", "SourceId", "FEN", "Threat", "Choices", "Refutations", "Good", "Rating", "Stage", "Motifs")
SOURCE = "lichess"

# Exercise kinds and the catalogue theme (src/services/themes.py) that tracks progress for each kind.
KINDS = ("threat", "blunder")
KIND_THEMES = {"threat": "find_the_threat", "blunder": "blunder_check"}
THEME_KINDS = {theme: kind for kind, theme in KIND_THEMES.items()}

# Selection criteria (centipawns from the defender's point of view).
DEFENSIBLE = -150        # the best defence does not lose: the position holds
THREAT_GAIN = 300        # "doing nothing" loses at least this much against the best defence -- the threat is real
THREAT_BEST_MARGIN = 50  # the puzzle's tactic is the opponent's best move (or nearly)
GOOD_MARGIN = 80         # a defence counts if it is almost as good as the best one
MAX_GOOD = 4             # few defences: a random move does not parry the threat
BLUNDER_LOSS = 300       # the losing option in "Don't blunder" loses at least this much against the best
LOSING = -200            # ...and really loses: "worse than the best but still +3" is not a blunder
NATURAL_GAP = 300        # a "natural" move: in a shallow search no worse than the best by more than this
NATURAL_CANDIDATES = 6   # how many of the most natural moves to check deeply as a trap
VERIFY_MARGIN = 200      # re-check: the correct move is better than the wrong ones (and "doing nothing") by at least this
MATE = 10_000            # mate score in centipawns -- the build script uses it to replace the engine's "mate in N"

# How long the record of an exercise being solved lives in Redis: after two hours without an answer the exercise must be
# taken again.
SESSION_TTL_S = 2 * 60 * 60
# How many recently served exercises are remembered, so as not to repeat them while others are available.
RECENT_KEPT = 200

# Best moves of a position: uci -> (score from the mover's point of view, opponent's reply from the main line).
MoveScores = dict[str, tuple[int, str | None]]
# analyse(position, how many best moves, only among these moves or all) -- the engine when building, a table in tests.
Analyse = Callable[[chess.Board, int, list[str] | None], MoveScores]


# --- building exercises from a puzzle ------------------------------------------------------------------------

def defender_position(fen: str, moves: list[str]) -> chess.Board | None:
    """
    The "What does the opponent threaten?" position: after the mistake moves[0] it is again the erring side's move (a null
    move by the opponent).
    None if that is impossible: the mistake gave check or the null move leaves the king in check.
    """
    board = chess.Board(fen)
    board.push_uci(moves[0])
    if board.is_check():
        return None
    board.push(chess.Move.null())
    if board.is_check() or not board.is_valid() or board.legal_moves.count() < 2:
        return None
    return chess.Board(board.fen())  # without history: the null move must not end up on the position's stack


def threat_drill(fen: str, moves: list[str], analyse: Analyse) -> dict | None:
    """
    The "What does the opponent threaten?" exercise, or None if the position fails the solvability criteria: the puzzle's
    tactic is
    the opponent's best move or nearly so (THREAT_BEST_MARGIN); the best defence holds the position (DEFENSIBLE) and beats
    "doing nothing" by at least THREAT_GAIN; good defences (within GOOD_MARGIN of the best) number from one to MAX_GOOD
    and no more than a third of all legal moves. Returns the position, the threat move and the list of accepted defences.
    """
    defender = defender_position(fen, moves)
    if defender is None:
        return None
    attacker = chess.Board(fen)
    attacker.push_uci(moves[0])
    threat = moves[1]
    attack = analyse(attacker, 1, None)
    if not attack:
        return None
    threat_score = attack[threat][0] if threat in attack else analyse(attacker, 1, [threat]).get(threat, (None,))[0]
    if threat_score is None or threat_score < max(s for s, _ in attack.values()) - THREAT_BEST_MARGIN:
        return None
    passing = -threat_score  # if the defender "does nothing", the opponent carries out the tactic
    # We look at one more best defence than allowed: if it is "good" too, there are too many defences.
    defense = analyse(defender, MAX_GOOD + 1, None)
    if not defense:
        return None
    best = max(s for s, _ in defense.values())
    if best < DEFENSIBLE or best - passing < THREAT_GAIN:
        return None
    good = sorted(uci for uci, (s, _) in defense.items() if s >= best - GOOD_MARGIN)
    if not 1 <= len(good) <= MAX_GOOD or len(good) * 3 > defender.legal_moves.count():
        return None
    return {"fen": defender.fen(), "threat": threat, "good": good}


def blunder_drill(fen: str, moves: list[str], analyse: Analyse, shallow: Analyse, seed: str) -> dict | None:
    """
    The "Don't blunder" exercise: the blunder from the game, another natural losing move and the single safe one.
    None if the position fails the criteria (already lost, the blunder does not lose, no natural trap).
    Naturalness is the shallow-search score (``shallow``): a move that is "by eye" no worse than the best.
    """
    board = chess.Board(fen)
    blunder = moves[0]
    top = analyse(board, 1, None)
    if not top:
        return None
    safe = next(iter(top))
    best = top[safe][0]
    if safe == blunder or best < DEFENSIBLE:
        return None
    looks = shallow(board, board.legal_moves.count(), None)
    if not looks:
        return None
    top_look = max(s for s, _ in looks.values())
    natural = sorted((uci for uci, (s, _) in looks.items()
                      if uci not in (safe, blunder) and s >= top_look - NATURAL_GAP),
                     key=lambda uci: (-looks[uci][0], uci))[:NATURAL_CANDIDATES]
    if not natural:
        return None
    scores = analyse(board, len(natural) + 1, [blunder, *natural])
    if blunder not in scores or scores[blunder][0] > min(best - BLUNDER_LOSS, LOSING):
        return None
    traps = [uci for uci in natural if uci in scores and scores[uci][0] <= min(best - BLUNDER_LOSS, LOSING)]
    if not traps:
        return None
    trap = traps[0]  # the most natural of the losing moves
    refutations = {uci: scores[uci][1] for uci in (blunder, trap)}
    if not all(refutations.values()):
        return None
    choices = [safe, blunder, trap]
    random.Random(seed).shuffle(choices)
    return {"fen": board.fen(), "choices": choices, "good": [safe], "refutations": refutations}


def verify_drill(row: dict, score_after: Callable[[str, str], int], *, margin: int = VERIFY_MARGIN,
                 losing: int = LOSING) -> bool:
    """
    Independent re-check of an exercise (deeper and with clean engine memory, unlike at selection): in endgames and positions
    with
    zugzwang the shallow-search score is unstable, and the "safe" move may turn out worse than the "losing" one.
    ``score_after(fen, uci)`` -- the score after the move from the point of view of the side to move in fen. In "Don't
    blunder" the wrong
    moves must really lose (no higher than ``losing``), not merely be inferior to the safe one. Tests on another
    engine version pass soft ``margin`` / ``losing``: borderline scores differ between versions.
    """
    good = row["Good"].split()
    if row["Kind"] == "blunder":
        safe = score_after(row["FEN"], good[0])
        wrong = set(row["Choices"].split()) - set(good)
        return safe >= DEFENSIBLE and all(score_after(row["FEN"], uci) <= min(safe - margin, losing)
                                          for uci in wrong)
    defenses = [score_after(row["FEN"], uci) for uci in good]
    if min(defenses) < DEFENSIBLE:
        return False
    passing = chess.Board(row["FEN"])
    passing.push(chess.Move.null())
    threat = -score_after(passing.fen(), row["Threat"])  # the opponent's score -> the defender's point of view
    return threat <= min(defenses) - margin


# --- sample and loading into the database -----------------------------------------------------------------------

def read_drills(path: pathlib.Path = DRILLS_FILE) -> Iterator[dict]:
    """Rows of the sample file as dicts with the FIELDS columns (all values are strings)."""
    with gzip.open(path, "rt", encoding="utf-8", newline="") as source:
        yield from csv.DictReader(source)


def write_drills(rows: Iterable[dict], path: pathlib.Path = DRILLS_FILE) -> int:
    """
    Writes the defence exercises to a compressed CSV (by default data/puzzles/defense_drills.csv.gz) and returns the number of
    rows. Called by the build script.
    """
    count = 0
    with gzip.open(path, "wt", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def validate_drill_row(row: dict) -> bool:
    """
    The position is valid, the moves are legal, "Don't blunder" has exactly one correct of three, for a threat it is legal
    for the opponent.
    """
    try:
        board = chess.Board(row["FEN"])
        if not board.is_valid() or row["Kind"] not in KINDS:
            return False
        legal = {m.uci() for m in board.legal_moves}
        good = row["Good"].split()
        if not good or not set(good) <= legal:
            return False
        if row["Kind"] == "threat":
            opponent = board.copy(stack=False)
            opponent.push(chess.Move.null())
            return chess.Move.from_uci(row["Threat"]) in opponent.legal_moves
        choices = row["Choices"].split()
        refutations = dict(pair.split(":") for pair in row["Refutations"].split())
        return (len(choices) == 3 and set(choices) <= legal and len(set(choices) & set(good)) == 1
                and set(refutations) == set(choices) - set(good))
    except (ValueError, KeyError):
        return False


def _drill_fields(row: dict) -> dict:
    """Sample row -> the defense_drills table column values (except the kind and the source puzzle id)."""
    return {
        "fen": row["FEN"], "threat": row["Threat"] or None, "choices": row["Choices"],
        "refutations": row["Refutations"], "good_moves": row["Good"], "rating": int(row["Rating"]),
        "stage": int(row["Stage"]), "motifs": row["Motifs"],
    }


async def import_drills(db: AsyncSession, rows: Iterable[dict], *, prune: bool = True) -> dict[str, int]:
    """
    Synchronises exercises with the sample: new ones are added, changed ones (a rebuilt sample) are updated, and those
    no longer in the sample (rejected by the re-check) are deleted -- otherwise a rejected exercise would remain
    on the server forever. Invalid rows are skipped. ``prune=False`` -- only add and update.
    An exercise is identified by the pair (kind, source puzzle id). Returns the counters added / updated / removed /
    invalid; after writing, the cache of puzzle counts per stage is reset (puzzles.reset_stage_counts).
    """
    existing = {(d.kind, d.source_id): d for d in (await db.execute(select(DefenseDrill))).scalars()}
    seen: set[tuple[str, str]] = set()
    report = {"added": 0, "updated": 0, "removed": 0, "invalid": 0}
    for row in rows:
        if not validate_drill_row(row):
            report["invalid"] += 1
            continue
        key = (row["Kind"], row["SourceId"])
        if key in seen:
            continue
        seen.add(key)
        fields = _drill_fields(row)
        drill = existing.get(key)
        if drill is None:
            db.add(DefenseDrill(kind=row["Kind"], source=SOURCE, source_id=row["SourceId"], **fields))
            report["added"] += 1
        elif any(getattr(drill, name) != value for name, value in fields.items()):
            for name, value in fields.items():
                setattr(drill, name, value)
            report["updated"] += 1
    if prune:
        for key, drill in existing.items():
            if key not in seen:
                await db.delete(drill)
                report["removed"] += 1
    await db.commit()
    reset_stage_counts()
    return report


async def stage_counts(db: AsyncSession) -> dict[tuple[str, int], int]:
    """How many exercises each section I theme has at each stage -- for the training overview."""
    rows = await db.execute(select(DefenseDrill.kind, DefenseDrill.stage, func.count())
                            .group_by(DefenseDrill.kind, DefenseDrill.stage))
    return {(KIND_THEMES[kind], stage): count for kind, stage, count in rows}


# --- solving -------------------------------------------------------------------------------------------------

@dataclass
class DrillSession:
    """The exercise the player is solving now (one per player; stored in Redis, key defense:session:{user_id})."""
    drill_id: int
    phase: str             # threat -- show the threat; move -- defend (or choose a move in "Don't blunder")
    clean: bool = True     # no mistake in the first phase


def _session_key(user_id: int) -> str:
    return f"defense:session:{user_id}"


def _recent_key(user_id: int) -> str:
    return f"defense:recent:{user_id}"


async def _load_session(user_id: int) -> DrillSession | None:
    raw = await redis_module.redis_client.get(_session_key(user_id))
    return DrillSession(**json.loads(raw)) if raw else None


async def _save_session(user_id: int, session: DrillSession) -> None:
    await redis_module.redis_client.set(_session_key(user_id), json.dumps(asdict(session)), ex=SESSION_TTL_S)


def defender_color(drill: DefenseDrill) -> str:
    return "white" if drill.fen.split()[1] == "w" else "black"


def public_view(drill: DefenseDrill) -> dict:
    """
    What the player sees: position, their colour, stage; for "Don't blunder" -- three moves. No threat and no correct
    answers.
    """
    return {
        "id": drill.id,
        "kind": drill.kind,
        "theme": KIND_THEMES[drill.kind],
        "fen": drill.fen,
        "color": defender_color(drill),
        "rating": drill.rating,
        "stage": drill.stage,
        "choices": drill.choices.split() if drill.kind == "blunder" else [],
    }


async def _current_stage(db: AsyncSession, user_id: int, kind: str) -> int:
    """
    The player's stage in the theme of this exercise kind (theme_progress), no higher than 4; without progress -- the first.
    """
    progress = await db.get(ThemeProgress, (user_id, KIND_THEMES[kind]))
    return min(progress.stage, 4) if progress else 1


async def pick(db: AsyncSession, user: User, kind: str) -> DefenseDrill:
    """
    An exercise of the given kind at the player's stage, excluding recent ones; if there are not enough -- a repeat of a
    recent one at their stage, then any
    exercise of this kind. The chosen one becomes active (the previously active one is forgotten) and enters the recent list.
    """
    if kind not in KINDS:
        raise PuzzleError("unknown_drill_kind", 400, kind=kind)
    stage = await _current_stage(db, user.id, kind)
    recent = [int(x) for x in await redis_module.redis_client.lrange(_recent_key(user.id), 0, -1)]
    attempts = ((True, True), (True, False), (False, False))  # (own stage, exclude recent)
    for own_stage, exclude in attempts:
        query = select(DefenseDrill).where(DefenseDrill.kind == kind)
        if own_stage:
            query = query.where(DefenseDrill.stage == stage)
        if exclude and recent:
            query = query.where(DefenseDrill.id.not_in(recent))
        drill = await db.scalar(query.order_by(func.random()).limit(1))
        if drill is not None:
            break
    else:
        raise PuzzleError("no_puzzles_available", 404)
    await _save_session(user.id, DrillSession(drill.id, "threat" if kind == "threat" else "move"))
    await redis_module.redis_client.lpush(_recent_key(user.id), str(drill.id))
    await redis_module.redis_client.ltrim(_recent_key(user.id), 0, RECENT_KEPT - 1)
    return drill


async def _active(db: AsyncSession, user: User, drill_id: int, phase: str) -> tuple[DrillSession, DefenseDrill]:
    """
    The player's active exercise and its record, if it is exactly drill_id and the current phase is phase. Another exercise
    or an
    expired record -- drill_not_active, another phase -- drill_wrong_step: only the served exercise can be answered
    and only in phase order.
    """
    session = await _load_session(user.id)
    if session is None or session.drill_id != drill_id:
        raise PuzzleError("drill_not_active", 409, drill_id=drill_id)
    if session.phase != phase:
        raise PuzzleError("drill_wrong_step", 409, step=session.phase)
    drill = await db.get(DefenseDrill, drill_id)
    if drill is None:
        await redis_module.redis_client.delete(_session_key(user.id))
        raise PuzzleError("drill_not_active", 409, drill_id=drill_id)
    return session, drill


def _square(name: str) -> str:
    try:
        return chess.square_name(chess.parse_square(name))
    except ValueError:
        raise PuzzleError("invalid_square", 400, square=name) from None


async def show_threat(db: AsyncSession, user: User, drill_id: int, square: str) -> dict:
    """
    First phase of "What does the opponent threaten?": correct -- the attacking piece or the target square. The threat is
    always revealed.
    """
    session, drill = await _active(db, user, drill_id, "threat")
    threat = drill.threat or ""
    correct = _square(square) in (threat[:2], threat[2:4])
    session.phase, session.clean = "move", correct
    await _save_session(user.id, session)
    return {"correct": correct, "threat": threat, "motifs": drill.motifs.split()}


async def answer(db: AsyncSession, user: User, drill_id: int, uci: str) -> dict:
    """
    The defence move (or the choice in "Don't blunder"): the outcome, correct moves, refutations and topic progress. Only a
    correct
    move with a correctly shown threat counts "clean" towards progress.
    """
    session, drill = await _active(db, user, drill_id, "move")
    board = chess.Board(drill.fen)
    try:
        move = chess.Move.from_uci(uci)
    except ValueError:
        raise DomainValueError("illegal_move", move=uci) from None
    if move not in board.legal_moves:
        raise DomainValueError("illegal_move", move=uci)
    if drill.kind == "blunder" and uci not in drill.choices.split():
        raise PuzzleError("drill_not_a_choice", 400, move=uci)

    good = drill.good_moves.split()
    correct = uci in good
    clean = correct and session.clean
    progress = await update_theme_progress(db, user.id, KIND_THEMES[drill.kind], drill.stage, clean=clean)
    await db.commit()
    await redis_module.redis_client.delete(_session_key(user.id))
    refutations = dict(pair.split(":") for pair in drill.refutations.split()) if drill.refutations else {}
    return {
        "correct": correct,
        "clean": clean,
        "good": good,
        "threat": drill.threat,
        "refutations": refutations,
        "motifs": drill.motifs.split(),
        "training": progress,
    }
