# --- FILE: scripts/trace_logs.py ---
"""
Log analysis (src/core/logging_setup.py): shows the chronology of events by one key - player, game, request
number, tournament - to reproduce a complaint such as "my game disappeared".

Where it reads from: json log files (in development - logs/api.jsonl and logs/worker.jsonl, written by start_dev.ps1) or
standard input (`docker compose logs --no-log-prefix api worker | python scripts/trace_logs.py game_id=7`).
Lines not in json format (foreign libraries, tracebacks) are skipped.

    python scripts/trace_logs.py game_id=20767 logs/api.jsonl logs/worker.jsonl
    python scripts/trace_logs.py request_id=8906cace68764324 logs/api.jsonl
    python scripts/trace_logs.py user_id=1 --level WARNING logs/api.jsonl

Chain from a client report: find the client_error line, take related_request_ids and trace each number with the same command.
"""

import argparse
import json
import sys
from collections.abc import Iterable, Iterator

LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
# Fields that are not repeated in the line's tail: they are already at its start.
_HEAD_FIELDS = {"ts", "level", "logger", "component", "msg"}


def parse_lines(lines: Iterable[str]) -> Iterator[dict]:
    """Json records from log lines; non-json ones are skipped."""
    for line in lines:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and "msg" in row:
            yield row


def matches(row: dict, wanted: dict[str, str], min_level: str = "DEBUG") -> bool:
    """A record matches if all field=value pairs match (a number and a string are compared as strings)
    and its level is not below min_level. A value in a list (related_request_ids) matches by membership."""
    if LEVELS.index(row.get("level", "INFO")) < LEVELS.index(min_level):
        return False
    for key, value in wanted.items():
        have = row.get(key)
        if isinstance(have, list):
            if value not in {str(item) for item in have}:
                return False
        elif str(have) != value:
            return False
    return True


def render(row: dict) -> str:
    """One chronology line: time, level, source, message and the other fields."""
    tail = " ".join(f"{key}={value}" for key, value in row.items() if key not in _HEAD_FIELDS and key != "exc")
    source = f"{row.get('component', '?')}/{row.get('logger', '?')}"
    line = f"{row.get('ts', '?')} {row.get('level', '?'):<7} {source}: {row['msg']}"
    if tail:
        line += f"  {tail}"
    if row.get("exc"):
        line += "\n" + str(row["exc"])
    return line


def trace(lines: Iterable[str], wanted: dict[str, str], min_level: str = "DEBUG") -> list[str]:
    """A filtered and time-ordered chronology (the lines are already rendered)."""
    rows = [row for row in parse_lines(lines) if matches(row, wanted, min_level)]
    rows.sort(key=lambda row: row.get("ts", ""))
    return [render(row) for row in rows]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chronology of events from the Regence json log")
    parser.add_argument("filters", nargs="+", help="field=value, for example game_id=7; then the log files")
    parser.add_argument("--level", default="DEBUG", choices=LEVELS, help="minimum level")
    args = parser.parse_args(argv)
    wanted: dict[str, str] = {}
    files: list[str] = []
    for item in args.filters:
        if "=" in item:
            key, _, value = item.partition("=")
            wanted[key] = value
        else:
            files.append(item)
    if not wanted:
        parser.error("at least one field=value filter is required")
    if files:
        lines: list[str] = []
        for path in files:
            with open(path, encoding="utf-8") as handle:
                lines.extend(handle)
    else:
        lines = list(sys.stdin)
    out = trace(lines, wanted, args.level)
    print("\n".join(out) if out else "nothing found")
    return 0 if out else 1


if __name__ == "__main__":
    sys.exit(main())
