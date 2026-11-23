# --- FILE: src/services/generated_drills.py ---
"""
Generator exercises (task 13.7): serving, answer checking, the one-minute run and personal records.

The position is not stored: an exercise is the key "kind.piece.level.seed", the server restores it with the generator
(src/services/drill_generator.py) and checks the answer. Seeds are taken from the table data/drills/seeds.json -- pre-selected
positions with a single answer. Mate in 2 takes two moves: after the first correct one the server replies with the opponent's
most stubborn
move, then any mate is counted.

The timed run (RUN_SECONDS, three mistakes end it) is kept on the server: the score grows only for an exercise issued in
this run; the best score per "kind.piece.level" combination is a personal record (the drill_records table). A running run is
the Redis record drills:run:{user_id}: the combination, end time, score, mistakes and the key of the issued exercise; a
player has one
run, a new one replaces the previous.
"""

import json
import pathlib
import random
import time

import chess
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import redis as redis_module
from src.models.puzzle import DrillRecord
from src.models.user import User
from src.services import drill_generator as gen
from src.services.puzzles import PuzzleError

# The table of verified seeds: "kind.piece.level" -> a list of seeds (built by scripts/dev/build_drill_seeds.py).
SEEDS_FILE = pathlib.Path(__file__).resolve().parents[2] / "data" / "drills" / "seeds.json"
# The timed run: the duration in seconds and the number of mistakes after which it ends.
RUN_SECONDS = 60
RUN_MISTAKES = 3
# A margin for network delay: an answer that arrives within these seconds after the run ends still counts.
RUN_GRACE_S = 2
# The link with the motif path (13.4): theme -> exercise kind (a button in the theme card).
THEME_DRILLS = {"hanging_piece": "capture", "fork": "fork", "pin": "pin", "basic_mates": "mate1"}

_seeds: dict[str, list[int]] | None = None


def seeds() -> dict[str, list[int]]:
    """The seed table from SEEDS_FILE; read from disk once per process."""
    global _seeds
    if _seeds is None:
        _seeds = json.loads(SEEDS_FILE.read_text(encoding="utf-8"))
    return _seeds


def combo(kind: str, piece: str, level: int) -> str:
    """
    The key of a "kind.piece.level" combination (the key of the seed table and of the record); an unknown combination --
    unknown_drill.
    """
    if not gen.supported(kind, piece) or level not in gen.LEVELS:
        raise PuzzleError("unknown_drill", 400, drill=f"{kind}/{piece}/{level}")
    return f"{kind}.{piece}.{level}"


def _color(fen: str) -> str:
    return "white" if fen.split()[1] == "w" else "black"


def view(drill: gen.Drill) -> dict:
    """
    An exercise for the client: position, whose move, which piece to solve with and how many moves are in the solution. The
    answer is not given.
    """
    board = chess.Board(drill.fen)
    moved = board.piece_at(chess.parse_square(drill.solutions[0][:2]))
    return {
        "key": drill.key, "kind": drill.kind, "piece": drill.piece, "level": drill.level,
        "fen": drill.fen, "color": _color(drill.fen),
        # Which piece to solve with (for a "random" one it becomes known from the puzzle); for "escape mate" -- any.
        "piece_type": None if drill.kind == "escape" or moved is None else moved.symbol().lower(),
        "moves": 2 if drill.kind == "mate2" else 1,
    }


def pick(kind: str, piece: str, level: int, rng: random.Random | None = None) -> gen.Drill:
    """
    A random exercise of a combination: seeds from the table in random order, the first for which the generator builds
    a position. If the combination has no usable seed -- no_puzzles_available.
    """
    table = seeds().get(combo(kind, piece, level)) or []
    for seed in (rng or random).sample(table, len(table)):
        drill = gen.build(kind, piece, level, seed)
        if drill is not None:  # the table was built by the same generator version -- a failure means it changed
            return drill
    raise PuzzleError("no_puzzles_available", 404)


def _restore(key: str) -> gen.Drill:
    try:
        return gen.restore(key)
    except ValueError:
        raise PuzzleError("unknown_drill", 400, drill=key) from None


def _legal(board: chess.Board, uci: str) -> chess.Move:
    try:
        move = chess.Move.from_uci(uci)
    except ValueError:
        raise PuzzleError("illegal_move", 400, move=uci) from None
    if move not in board.legal_moves:
        raise PuzzleError("illegal_move", 400, move=uci)
    return move


def full_line(drill: gen.Drill) -> list[str]:
    """The whole solution: one move, and in mate in 2 -- the first move, the stubborn reply and the mate."""
    if drill.kind != "mate2":
        return list(drill.solutions)
    board = chess.Board(drill.fen)
    first = chess.Move.from_uci(drill.solutions[0])
    reply = gen.mate_reply(board, first)
    board.push(first)
    board.push(reply)
    mate = min(m.uci() for m in board.legal_moves if _mates(board, m))
    return [first.uci(), reply.uci(), mate]


def _mates(board: chess.Board, move: chess.Move) -> bool:
    board.push(move)
    mate = board.is_checkmate()
    board.pop()
    return mate


def check(key: str, moves: list[str]) -> dict:
    """
    An answer to an exercise: moves -- the solver's moves and the opponent's replies in order (in mate in 2 -- first one move,
    then all three). Returns whether correct, whether finished, the opponent's reply (mate in 2) and the solution on a
    mistake. A wrong
    number of moves or a wrong opponent reply in the second request -- drill_wrong_step; an illegal move -- illegal_move.
    As the second move of mate in 2 any mating move is accepted.
    """
    drill = _restore(key)
    if not moves or len(moves) > 3 or (drill.kind != "mate2" and len(moves) != 1) or len(moves) == 2:
        raise PuzzleError("drill_wrong_step", 409, step=len(moves))
    board = chess.Board(drill.fen)
    first = _legal(board, moves[0])
    if first.uci() not in drill.solutions:
        return {"correct": False, "done": True, "reply": None, "solution": full_line(drill)}
    if drill.kind != "mate2":
        return {"correct": True, "done": True, "reply": None, "solution": None}
    reply = gen.mate_reply(board, first)
    if len(moves) == 1:
        return {"correct": True, "done": False, "reply": reply.uci(), "solution": None}
    if moves[1] != reply.uci():
        raise PuzzleError("drill_wrong_step", 409, step=2)
    board.push(first)
    board.push(reply)
    final = _legal(board, moves[2])
    if _mates(board, final):
        return {"correct": True, "done": True, "reply": None, "solution": None}
    return {"correct": False, "done": True, "reply": None, "solution": full_line(drill)}


# --- timed run ---------------------------------------------------------------------------------------------

def _run_key(user_id: int) -> str:
    return f"drills:run:{user_id}"


async def _load_run(user_id: int) -> dict | None:
    raw = await redis_module.redis_client.get(_run_key(user_id))
    return json.loads(raw) if raw else None


async def _save_run(user_id: int, run: dict) -> None:
    """
    Saves the run in Redis; the record lives 10 minutes longer than the run so that the result can be collected (finish_run).
    """
    await redis_module.redis_client.set(_run_key(user_id), json.dumps(run), ex=RUN_SECONDS + 600)


def _run_over(run: dict) -> bool:
    """The run is over: RUN_MISTAKES mistakes reached or time is out (with the RUN_GRACE_S margin)."""
    return run["mistakes"] >= RUN_MISTAKES or time.time() > run["ends_at"] + RUN_GRACE_S


def run_view(run: dict) -> dict:
    return {"combo": run["combo"], "solved": run["solved"], "mistakes": run["mistakes"],
            "seconds_left": max(0, round(run["ends_at"] - time.time())), "over": _run_over(run)}


async def start_run(user: User, kind: str, piece: str, level: int) -> dict:
    """Starts a timed run for a combination; the player's previous run, if any, is replaced."""
    run = {"combo": combo(kind, piece, level), "ends_at": time.time() + RUN_SECONDS,
           "solved": 0, "mistakes": 0, "current": None}
    await _save_run(user.id, run)
    return run_view(run)


async def next_in_run(user: User) -> tuple[gen.Drill, dict]:
    """The next exercise of the timed run. No run or it has ended -- a refusal."""
    run = await _load_run(user.id)
    if run is None:
        raise PuzzleError("timed_run_not_active", 409)
    if _run_over(run):
        raise PuzzleError("timed_run_over", 409)
    kind, piece, level = run["combo"].split(".")
    drill = pick(kind, piece, int(level))
    run["current"] = drill.key
    await _save_run(user.id, run)
    return drill, run_view(run)


async def answer(user: User, key: str, moves: list[str], *, in_run: bool) -> dict:
    """
    Answer checking; in a run a finished exercise (the one issued by the run) changes the score. An answer to an exercise
    that the run did not issue -- a refusal timed_run_not_active; an answer after the run ends is checked but does not change
    the score.
    """
    result = check(key, moves)
    result["run"] = None
    if in_run:
        run = await _load_run(user.id)
        if run is None or run.get("current") != key:
            raise PuzzleError("timed_run_not_active", 409)
        if result["done"] and not _run_over(run):
            run["solved" if result["correct"] else "mistakes"] += 1
            run["current"] = None
            await _save_run(user.id, run)
        result["run"] = run_view(run)
    return result


async def finish_run(db: AsyncSession, user: User) -> dict:
    """End of the run: score, mistakes and the personal record for the "kind.piece.level" combination (updated if beaten)."""
    run = await _load_run(user.id)
    if run is None:
        raise PuzzleError("timed_run_not_active", 409)
    await redis_module.redis_client.delete(_run_key(user.id))
    record = await db.get(DrillRecord, (user.id, run["combo"]))
    best = record.best if record else 0
    new_record = run["solved"] > best
    if new_record:
        if record is None:
            db.add(DrillRecord(user_id=user.id, combo=run["combo"], best=run["solved"]))
        else:
            record.best = run["solved"]
        await db.commit()
    return {"combo": run["combo"], "score": run["solved"], "mistakes": run["mistakes"],
            "best": max(best, run["solved"]), "new_record": new_record}


async def records(db: AsyncSession, user: User) -> dict[str, int]:
    """The player's personal records: the "kind.piece.level" combination -> the best run score (the drill_records table)."""
    rows = await db.execute(select(DrillRecord.combo, DrillRecord.best).where(DrillRecord.user_id == user.id))
    return {combo_key: best for combo_key, best in rows}
