# --- FILE: src/services/bots/calibration.py ---
"""
Measured strength of the bots (task 10.4): the result of scripts/calibrate_bots.py in calibration.json next to it.

Keys: id of a historical bot ("morphy") or "archetype:<name>". If a bot is not calibrated yet,
the declared rating is taken — and this is visible in the field measured=False.

Data: calibration.json (fields meta and players: key → rating, games, ci95) and the run logs in
scripts/calibration_runs/. They are read by src/api/bots.py and src/api/public.py (the page "How we measure bot strength") and
memory.py (the bot's initial rating).
"""

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# The result of the latest calibration (written by scripts/calibrate_bots.py).
CALIBRATION_PATH = Path(__file__).resolve().parent / "calibration.json"
# Calibration run logs (task 24.3, the page "How we measure bot strength"): who played whom and how it ended.
RUNS_DIR = Path(__file__).resolve().parents[3] / "scripts" / "calibration_runs"
# Valid log name: YYYY-MM-DD_name.log (protocol) or .pgn (games); the page serves no other files.
RUN_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})_([a-z0-9_]{1,60})\.(log|pgn)$")


@dataclass(frozen=True)
class Strength:
    """Bot strength: rating, whether it was measured by matches (measured), number of games and the 95 % confidence interval
    (+-)."""

    rating: int
    measured: bool
    games: int = 0
    ci95: int | None = None


@lru_cache(maxsize=1)
def load_calibration() -> dict:
    """Contents of calibration.json, cached per process; file missing or corrupt — an empty set {meta: None, players: {}}."""
    try:
        return json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"meta": None, "players": {}}


def strength_of(key: str, declared: int) -> Strength:
    """Bot strength by key: measured from calibration or, if there is none, the declared one (measured=False)."""
    entry = load_calibration().get("players", {}).get(key)
    if not entry:
        return Strength(rating=declared, measured=False)
    return Strength(
        rating=int(entry["rating"]), measured=True, games=int(entry.get("games", 0)), ci95=entry.get("ci95"),
    )


def runs() -> list[dict]:
    """Run logs, newest to oldest: file name, date, kind (log — protocol, pgn — games) and size."""
    if not RUNS_DIR.is_dir():
        return []
    found = []
    for path in RUNS_DIR.iterdir():
        match = RUN_NAME.match(path.name)
        if match and path.is_file():
            found.append({"name": path.name, "date": match.group(1), "title": match.group(2), "kind": match.group(3),
                          "size": path.stat().st_size})
    return sorted(found, key=lambda item: (item["date"], item["name"]), reverse=True)


def read_run(name: str) -> str | None:
    """Log text by a name from runs(); the name is checked against a pattern — the path cannot leave the folder."""
    if not RUN_NAME.match(name):
        return None
    path = RUNS_DIR / name
    try:
        return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else None
    except OSError:
        return None
