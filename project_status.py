#!/usr/bin/env python3
# --- FILE: project_status.py ---
"""
Project status summary for people and for the AI assistant: git, the plan (ToDo.md), migrations, bot calibration.

Used by make_snapshot.py (STATUS.md and the start of the snapshot), and also standalone:
    python project_status.py
Changes nothing and uses no network: it only reads files and local git.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

TASK_RE = re.compile(
    r"^### - \[(?P<done>[ x])\] \u0422\u0430\u0441\u043a "
    r"(?P<id>[0-9A-Za-z]+(?:\.[0-9a-z]+)?)\.\s*(?P<title>.*?)\s*(?:\(`[^`]+`\))?\s*$"
)
SECTION_RE = re.compile(r"^## (?P<title>.+?)\s*$")
# ToDo.md is Ukrainian (owner decision 23.11); its markers ("Task", "Sprint", "New order") are written as escapes
# to keep this code file free of Cyrillic.
ORDER_START = "**\u041d\u043e\u0432\u0438\u0439 \u043f\u043e\u0440\u044f\u0434\u043e\u043a"
# Task range: "A.1-A.8" or "17.1-17.4".
RANGE_RE = re.compile(r"\b([A-Z]|\d+)\.(\d+)\s*[–-]\s*(?:\1\.)?(\d+)\b")
TASK_ID_RE = re.compile(r"\b((?:[A-Z]|\d+)\.\d+[a-z]?)\b")
SPRINT_RE = re.compile(r"[\u0421\u0441]\u043f\u0440\u0438\u043d\u0442\s+(\d+)")


@dataclass
class Task:
    id: str
    title: str
    done: bool
    section: str


@dataclass
class Plan:
    tasks: list[Task] = field(default_factory=list)
    sections: dict[str, list[Task]] = field(default_factory=dict)
    priority: list[str] = field(default_factory=list)


def parse_plan(text: str) -> Plan:
    """ToDo.md tasks by section and the work order from the "New order" block."""
    plan = Plan()
    section = ""
    for line in text.splitlines():
        heading = SECTION_RE.match(line)
        if heading:
            section = heading.group("title")
            continue
        match = TASK_RE.match(line)
        if match:
            task = Task(match.group("id"), match.group("title"), match.group("done") == "x", section)
            plan.tasks.append(task)
            plan.sections.setdefault(section, []).append(task)

    start = text.find(ORDER_START)
    if start >= 0:
        block = text[start:].split("\n\n", 2)
        order_text = "\n".join(block[:2])
        for line in order_text.splitlines():
            if not re.match(r"^\s*\d+[a-z]?\.\s", line):
                continue
            ids: list[str] = []
            for prefix, first, last in RANGE_RE.findall(line):
                ids += [f"{prefix}.{n}" for n in range(int(first), int(last) + 1)]
            line_wo_ranges = RANGE_RE.sub("", line)
            ids += TASK_ID_RE.findall(line_wo_ranges)
            for sprint in SPRINT_RE.findall(line_wo_ranges):
                ids += [t.id for t in plan.tasks if t.id.split(".")[0] == sprint]
            for task_id in ids:
                if task_id not in plan.priority:
                    plan.priority.append(task_id)
    return plan


def next_tasks(plan: Plan, limit: int = 8) -> list[Task]:
    """Nearest open tasks: first in the "New order" sequence, then in file order."""
    by_id = {t.id: t for t in plan.tasks}
    ordered = [by_id[i] for i in plan.priority if i in by_id and not by_id[i].done]
    return ordered[:limit]


def _git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    # rstrip, not strip: the leading space of the first `git status --porcelain` line is significant.
    return result.stdout.rstrip() if result.returncode == 0 else ""


def git_status(root: Path) -> list[str]:
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD") or "?"
    head = _git(root, "log", "-1", "--format=%h %ci %s")
    dirty = [line for line in _git(root, "status", "--porcelain").splitlines() if line]
    ahead = _git(root, "rev-list", "--count", "@{u}..HEAD")
    behind = _git(root, "rev-list", "--count", "HEAD..@{u}")
    stashes = [line for line in _git(root, "stash", "list").splitlines() if line]
    recent = _git(root, "log", "-8", "--format=  %h %cs %s")
    lines = [
        f"- Branch: `{branch}`, last commit: {head or '—'}",
        f"- Not pushed to GitHub: {ahead or '?'} commit(s), not pulled: {behind or '?'}",
        f"- Uncommitted files: {len(dirty)}" + (f" (for example: {', '.join(d[3:] for d in dirty[:5])})" if dirty else ""),
        f"- Stash: {len(stashes)}",
    ]
    if recent:
        lines += ["- Recent commits:", "```", recent, "```"]
    return lines


def migration_head(root: Path) -> str:
    versions = root / "migrations" / "versions"
    revisions: dict[str, str] = {}
    downs: set[str] = set()
    for path in versions.glob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        rev = re.search(r'^revision[^=]*=\s*["\']([0-9a-f]+)["\']', text, re.M)
        down = re.search(r'^down_revision[^=]*=\s*["\']([0-9a-f]+)["\']', text, re.M)
        if rev:
            revisions[rev.group(1)] = path.stem
        if down:
            downs.add(down.group(1))
    heads = [f"{rev} ({name})" for rev, name in revisions.items() if rev not in downs]
    return ", ".join(sorted(heads)) or "—"


def calibration(root: Path) -> str:
    path = root / "src" / "services" / "bots" / "calibration.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "no calibration - the declared strength is shown"
    meta = data.get("meta") or {}
    players = data.get("players") or {}
    gaps = [abs(p["rating"] - p["declared"]) for p in players.values() if p.get("declared")]
    worst = max(gaps) if gaps else 0
    within = sum(1 for g in gaps if g <= 100)
    return (f"{meta.get('date', '?')}, {meta.get('games', '?')} games; "
            f"measured strength is within ±100 of the declared one for {within} of {len(gaps)} bots (worst gap {worst})")


def build_status(root: Path) -> str:
    todo = root / "ToDo.md"
    plan = parse_plan(todo.read_text(encoding="utf-8")) if todo.exists() else Plan()
    done = sum(t.done for t in plan.tasks)
    lines = [
        "# Project status",
        "",
        "_Generated by `project_status.py` from local files and git; do not edit by hand._",
        "",
        "## Git",
        *git_status(root),
        "",
        "## Plan (ToDo.md)",
        f"- Tasks: {len(plan.tasks)}, done {done}, remaining {len(plan.tasks) - done}",
        "",
        "Next in work order:",
    ]
    upcoming = next_tasks(plan)
    lines += [f"{i}. {t.id} — {t.title}" for i, t in enumerate(upcoming, 1)] or ["- (work order not found)"]
    lines += ["", "By section (done/total):"]
    for section, tasks in plan.sections.items():
        finished = sum(t.done for t in tasks)
        mark = "✅" if finished == len(tasks) else "⏳" if finished else "·"
        lines.append(f"- {mark} {section}: {finished}/{len(tasks)}")
    lines += [
        "",
        "## Server",
        f"- Migration head: {migration_head(root)}",
        f"- Bot calibration: {calibration(root)}",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    # The Windows console defaults to cp1251 and does not print emoji statuses (✅, ⏳).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(build_status(Path(__file__).resolve().parent))
