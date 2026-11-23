"""
Big Course level exams (task 27.12): a "rank test". For each level 0-5 -- a fixed set of positions by the
course branches (tactics T, mate and attack M, endgame E, strategy S, calculation C) from src/services/data/level_exams.json
(built by scripts/build_level_exams.py: CC0 database puzzles near the rank threshold, the answer verified by the engine --
the only one).
The test runs through the same protocol as diagnostic 22.0 (/exam/level<n>/questions, /move and /submit): a question is an id
by
order in the set, the solution (the moves field, if it is longer than one move) is played out to the end, any mate counts.
The result is a strength estimate by the Elo formula (src/services/exam.estimate), the level is passed when it is not below
the threshold
(client, supercourse.levelExamPassed), plus a profile by branch.

The exam is timed (time_limit_s): the deadline is reported by the server together with the questions, the countdown is kept
by the client, which submits the test itself
on expiry; positions the player did not reach score no points. As in the final check of the mate course.
"""

import json
from functools import lru_cache
from pathlib import Path

import chess

DATA = Path(__file__).resolve().parent / "data" / "level_exams.json"
# The beginning of a level exam section code: level0 ... level5.
PREFIX = "level"
# Course branches by which questions are labelled: tactics, mate and attack, endgame, strategy, calculation.
BRANCHES = ("T", "M", "E", "S", "C")
# Level exam time: seconds per position (the default decision 20.11 -- as in the mate course check, a minute per puzzle).
SECONDS_PER_POSITION = 60


@lru_cache(maxsize=1)
def levels() -> dict[str, dict]:
    """Question sets from the data file: section code ("level3") -> level record. The file is read once per process."""
    with DATA.open(encoding="utf-8") as handle:
        return {f"{PREFIX}{item['level']}": item for item in json.load(handle)}


def sections() -> list[str]:
    return list(levels())


def is_level_section(section: str) -> bool:
    return section in levels()


def questions(section: str) -> list[dict]:
    """
    The level's questions for the client -- without answers; a question id is its ordinal number in the set, starting from 1.
    """
    return [{"id": index, "fen": q["fen"], "color": "white" if chess.Board(q["fen"]).turn else "black",
             "previous_move": q["previous_move"], "branch": q["branch"]}
            for index, q in enumerate(levels()[section]["questions"], 1)]


def time_limit_s(section: str) -> int | None:
    """The level exam time in seconds (SECONDS_PER_POSITION per position); other tests have no time -- None."""
    if not is_level_section(section):
        return None
    return SECONDS_PER_POSITION * len(levels()[section]["questions"])


def question(section: str, question_id: int) -> dict | None:
    """The full question record (with the answer) by number in the set; numbers outside the set -- None."""
    items = levels()[section]["questions"]
    return items[question_id - 1] if 1 <= question_id <= len(items) else None


def progress(item: dict, played: list[str]):
    """
    Checking the player's moves against the question solution (src/services/exam.play); without the moves field the solution
    is one move.
    """
    from src.services.exam import play

    return play(chess.Board(item["fen"]), item.get("moves") or [item["answer"]], played)


def is_correct(item: dict, uci: str) -> bool:
    return progress(item, [uci]).correct > 0


def branch_profile(review: list[dict]) -> dict[str, dict]:
    """Correct / total by branch -- for the result and the skills map."""
    profile: dict[str, dict] = {}
    for row in review:
        entry = profile.setdefault(row["branch"], {"correct": 0, "total": 0})
        entry["total"] += 1
        entry["correct"] += int(row["correct"])
    return profile
