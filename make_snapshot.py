#!/usr/bin/env python3
# --- FILE: make_snapshot.py ---
"""
Create an LLM-ready multi-part text snapshot of the project.

Run from the project root:
    python make_snapshot.py                  # full snapshot (code first, tests last)
    python make_snapshot.py --no-tests       # working code and configs only (~13-15 parts, fits into the context whole)
    python make_snapshot.py --scope backend  # backend only (ToDo, migrations, src, scripts)
    python make_snapshot.py --scope frontend # frontend only
    python make_snapshot.py --status         # project status summary only, no snapshot

Each part is capped at 80 KiB by default so chat attachments are never
truncated by upload limits.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

DEFAULT_MAX_KB = 80
OUTPUT_DIR_NAME = "_project_snapshot"
MAX_DATA_JSON_BYTES = 15 * 1024  # Collapse large JSON files (> 15 KB)
SAFE_CONTEXT_TOKENS = 260_000  # Safe token threshold for one chat window without evicting earlier parts

EXCLUDED_DIRS = {
    ".git", ".hg", ".svn",
    ".idea", ".vscode",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".tox", ".nox",
    ".venv", "venv", "env",
    "node_modules", "bower_components",
    "dist", "build", "target", "coverage", "htmlcov",
    ".next", ".nuxt", ".cache",
    "site-packages", "vendor",
    "bin", "downloaded_pgns", "data",
    "playwright-report", "test-results", "blob-report",
    OUTPUT_DIR_NAME,
}

EXCLUDED_FILES = {
    "package-lock.json", "npm-shrinkwrap.json",
    "yarn.lock", "pnpm-lock.yaml", "bun.lockb", "bun.lock",
    ".env", ".env.local", ".env.development", ".env.production",
    ".env.test", ".env.staging",
    "id_rsa", "id_ed25519", "known_hosts",
    "unreadable_files.txt",
    "style_bonus_golden.json",
    # Duplicate localization dictionaries (the full structure and texts stay in ru.ts)
    "en.ts", "uk.ts",
}

EXCLUDED_SUFFIXES = {
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".exe", ".bin",
    ".db", ".sqlite", ".sqlite3",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg",
    ".pdf", ".zip", ".7z", ".rar", ".tar", ".gz",
    ".mp3", ".mp4", ".mov", ".avi", ".wav",
    ".ttf", ".otf", ".woff", ".woff2",
    ".class", ".jar", ".war", ".pgn",
}

TEXT_SUFFIXES = {
    ".py", ".pyi",
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
    ".json", ".jsonc", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".md", ".rst", ".txt",
    ".sql", ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd",
    ".Mako", ".mako",
}

TEXT_FILENAMES = {
    "Dockerfile", "Makefile", "Procfile", "Justfile",
    ".gitignore", ".dockerignore", ".editorconfig",
    ".prettierrc", ".eslintrc", ".npmrc", "README",
}

SECRET_PATH_PARTS = {
    "secrets", "secret", "credentials", "private",
}

PRIORITY_FILES = [
    "ToDo.md",
    "pyproject.toml",
    "uv.lock",
    "pyproject.toml",
    "pytest.ini",
    "alembic.ini",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.prod.yml",
    ".github/workflows/ci.yml",
    "frontend/package.json",
    "frontend/vite.config.ts",
    "frontend/tsconfig.json",
]


def is_test_file(relative_posix: str) -> bool:
    """Tells whether a file belongs to the tests (backend, frontend, e2e)."""
    lower = relative_posix.lower()
    parts = lower.split("/")
    filename = parts[-1]
    if lower.startswith("tests/") or lower.startswith("frontend/e2e/"):
        return True
    if "__tests__" in parts or "test" in parts:
        return True
    return filename.startswith("test_") or ".test." in filename or ".spec." in filename or ".e2e." in filename


def is_text_candidate(
        path: Path,
        relative: str,
        *,
        no_tests: bool = False,
        include_all_i18n: bool = False,
        scope: str = "all",
) -> bool:
    name = path.name
    name_lower = name.lower()
    suffix = path.suffix.lower()
    rel_posix = relative.replace("\\", "/")
    rel_lower = rel_posix.lower()
    rel_parts = {part.lower() for part in Path(rel_posix).parts}

    if name in EXCLUDED_FILES and not (include_all_i18n and name in {"en.ts", "uk.ts"}):
        return False
    if "snapshot" in name_lower and suffix == ".txt":
        return False
    if name_lower.endswith("_generated_book.json"):
        return False
    if suffix in EXCLUDED_SUFFIXES:
        return False
    if rel_parts & SECRET_PATH_PARTS:
        return False
    if re.search(r"(^|/)\.env(?:\.|$)", rel_posix, re.I):
        return False

    if (no_tests or scope == "code") and is_test_file(rel_posix):
        return False

    if scope == "backend" and rel_lower.startswith("frontend/"):
        return False
    if scope == "frontend" and rel_lower.startswith(("src/", "tests/", "migrations/", "scripts/")):
        return False

    if suffix in TEXT_SUFFIXES or name in TEXT_FILENAMES:
        return True

    if not suffix:
        try:
            sample = path.read_bytes()[:4096]
        except OSError:
            return False
        return b"\x00" not in sample

    return False


def get_group_priority(relative_posix: str) -> tuple[int, str]:
    """
    Orders the files so that ALL working code goes into the first parts
    and the tests into the very end:
    0..N - priority manifests (ToDo.md, pyproject.toml, etc.)
    100  - DB migrations (migrations/)
    200  - backend source code (src/)
    300  - frontend source code without tests (frontend/src/)
    400  - scripts and documentation (scripts/, docs/, *.md)
    500  - backend tests (tests/)
    600  - frontend tests and E2E (frontend/**/__tests__, *.test.*, frontend/e2e/)
    """
    lower = relative_posix.lower()
    for idx, prio_name in enumerate(PRIORITY_FILES):
        if lower == prio_name.lower():
            return (idx, lower)

    if is_test_file(relative_posix):
        if lower.startswith("tests/"):
            return (500, lower)
        return (600, lower)

    if lower.startswith("migrations/"):
        return (100, lower)
    if lower.startswith("src/"):
        return (200, lower)
    if lower.startswith("frontend/"):
        return (300, lower)
    if lower.startswith(("scripts/", "docs/")):
        return (400, lower)
    return (450, lower)


def collect_files(
        root: Path,
        *,
        no_tests: bool = False,
        include_all_i18n: bool = False,
        scope: str = "all",
) -> list[Path]:
    files: list[Path] = []

    for current, dirs, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirs[:] = sorted(
            d for d in dirs
            if d not in EXCLUDED_DIRS
            and not (current_path / d).is_symlink()
        )

        for filename in filenames:
            path = current_path / filename
            if path.is_symlink() or not path.is_file():
                continue

            relative = path.relative_to(root).as_posix()
            if is_text_candidate(
                    path,
                    relative,
                    no_tests=no_tests,
                    include_all_i18n=include_all_i18n,
                    scope=scope,
            ):
                files.append(path)

    return sorted(files, key=lambda p: get_group_priority(p.relative_to(root).as_posix()))


def decode_file(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace")


def _truncate_json_value(value: Any, max_items: int = 3, depth: int = 0) -> Any:
    """Recursively collapses long lists and dicts inside large JSON files."""
    if depth > 4:
        return "..."
    if isinstance(value, dict):
        items = list(value.items())
        result = {k: _truncate_json_value(v, max_items=max_items, depth=depth + 1) for k, v in items[:max_items]}
        if len(items) > max_items:
            result[f"... (+{len(items) - max_items} keys)"] = "..."
        return result
    if isinstance(value, list):
        if len(value) <= max_items:
            return [_truncate_json_value(v, max_items=max_items, depth=depth + 1) for v in value]
        head = [_truncate_json_value(v, max_items=max_items, depth=depth + 1) for v in value[:max_items]]
        head.append(f"... (+{len(value) - max_items} items)")
        return head
    return value


def maybe_summarize_large_json(path: Path, relative: str, content: str, full_json: bool) -> str:
    """
    If this is a large JSON file (> 15 KB), collapses its structure (including nested lists)
    to the first 3 elements at every level so that data does not clog the context.
    """
    if full_json or path.suffix.lower() != ".json":
        return content

    raw_size = len(content.encode("utf-8"))
    if raw_size <= MAX_DATA_JSON_BYTES:
        return content

    try:
        parsed = json.loads(content)
        summarized = _truncate_json_value(parsed, max_items=3)
        sample_str = json.dumps(summarized, ensure_ascii=False, indent=2)
        return (
            f"// [AUTO-SUMMARY: Large JSON file ({raw_size // 1024} KiB). "
            f"Only the first 3 elements of each level are shown. Run with --full-json for the full output]\n"
            f"{sample_str}"
        )
    except Exception:
        return content


def make_file_blocks(
        root: Path,
        files: list[Path],
        full_json: bool = False,
) -> tuple[list[tuple[str, str]], list[str]]:
    blocks: list[tuple[str, str]] = []
    unreadable: list[str] = []

    for path in files:
        relative = path.relative_to(root).as_posix()
        try:
            content = decode_file(path)
        except OSError as exc:
            unreadable.append(f"{relative}: {exc}")
            continue

        content = content.replace("\r\n", "\n").replace("\r", "\n")
        content = maybe_summarize_large_json(path, relative, content, full_json)

        sep = "=" * 88
        block = (
            f"\n{sep}\n"
            f"FILE: {relative}\n"
            f"{sep}\n"
            f"{content.rstrip()}\n"
        )
        blocks.append((relative, block))

    return blocks, unreadable


def split_oversized_block(relative: str, block: str, max_bytes: int) -> list[tuple[str, str]]:
    """Splits one very large file at line boundaries if it alone exceeds the part limit."""
    if len(block.encode("utf-8")) <= max_bytes:
        return [(relative, block)]

    pieces: list[tuple[str, str]] = []
    remaining = block
    part_idx = 1

    while remaining:
        low, high = 1, len(remaining)
        best = 1

        while low <= high:
            middle = (low + high) // 2
            size = len(remaining[:middle].encode("utf-8"))
            if size <= max_bytes:
                best = middle
                low = middle + 1
            else:
                high = middle - 1

        if best < len(remaining):
            newline = remaining.rfind("\n", 0, best)
            if newline > best // 2:
                best = newline + 1

        chunk_text = remaining[:best]
        label = f"{relative} (chunk {part_idx})"
        pieces.append((label, chunk_text))
        remaining = remaining[best:]
        part_idx += 1

    return pieces


def pack_parts(
        blocks: list[tuple[str, str]],
        max_bytes: int,
) -> list[tuple[list[str], str]]:
    """Packs file blocks into parts so that each part is strictly <= max_bytes."""
    chunks: list[tuple[str, str]] = []
    for relative, block in blocks:
        chunks.extend(split_oversized_block(relative, block, max_bytes))

    parts: list[tuple[list[str], str]] = []
    current_files: list[str] = []
    current_texts: list[str] = []
    current_size = 0

    for label, chunk in chunks:
        chunk_size = len(chunk.encode("utf-8"))
        if current_texts and current_size + chunk_size > max_bytes:
            parts.append((current_files, "".join(current_texts)))
            current_files = []
            current_texts = []
            current_size = 0

        current_files.append(label)
        current_texts.append(chunk)
        current_size += chunk_size

    if current_texts:
        parts.append((current_files, "".join(current_texts)))

    return parts or [([], "[No suitable text files found]\n")]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a multi-part project snapshot without truncation in chat."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Project root (current folder by default).",
    )
    parser.add_argument(
        "--max-kb",
        type=float,
        default=DEFAULT_MAX_KB,
        help=f"Maximum size of one part in KiB (default {DEFAULT_MAX_KB} KiB).",
    )
    parser.add_argument(
        "--max-mb",
        type=float,
        default=None,
        help="Alternative limit in MiB (overrides --max-kb if given).",
    )
    parser.add_argument(
        "--no-tests",
        action="store_true",
        help="Exclude all tests (tests/, __tests__/, e2e/, *.test.*) so that all the code fits into the AI context.",
    )
    parser.add_argument(
        "--scope",
        choices=("all", "code", "backend", "frontend"),
        default="all",
        help="Snapshot scope: all (everything), code (code without tests), backend, frontend.",
    )
    parser.add_argument(
        "--all-i18n",
        action="store_true",
        help="Include all language catalogs (en.ts, uk.ts, ru.ts), not just the reference ru.ts.",
    )
    parser.add_argument(
        "--full-json",
        action="store_true",
        help="Do not collapse large JSON opening books.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Only print the project status summary, no snapshot.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=f"Output folder (default ./{OUTPUT_DIR_NAME}).",
    )
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    if not root.is_dir():
        print(f"Error: folder not found: {root}", file=sys.stderr)
        return 2

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from project_status import build_status

    status = build_status(root)
    if args.status:
        print(status)
        return 0

    if args.max_mb is not None:
        max_kb = args.max_mb * 1024.0
    else:
        max_kb = args.max_kb

    if max_kb <= 10:
        print("Error: the part size must be greater than 10 KiB.", file=sys.stderr)
        return 2

    output = (
        args.output.expanduser().resolve()
        if args.output
        else root / OUTPUT_DIR_NAME
    )
    # Leave a 3 KiB reserve for the part header and footer
    max_bytes = max(8192, int(max_kb * 1024) - 3072)

    files = collect_files(
        root,
        no_tests=args.no_tests,
        include_all_i18n=args.all_i18n,
        scope=args.scope,
    )
    blocks, unreadable = make_file_blocks(root, files, full_json=args.full_json)
    parts = pack_parts(blocks, max_bytes)

    output.mkdir(parents=True, exist_ok=True)

    for old in output.glob("snapshot_[0-9][0-9][0-9].txt"):
        old.unlink()

    total_parts = len(parts)
    index_lines = [
        status,
        "=" * 88,
        f"PROJECT: {root.name} (scope={args.scope}, no_tests={args.no_tests})",
        f"ROOT: {root}",
        f"FILES INCLUDED: {len(blocks)}",
        f"PARTS: {total_parts} (target <= {max_kb:.0f} KiB per part)",
        "",
        "UPLOAD ALL PARTS IN NUMERICAL ORDER (snapshot_001.txt .. snapshot_00N.txt).",
        "",
        "TABLE OF CONTENTS BY PART:",
    ]

    print(f"Project: {root} (mode: scope={args.scope}, no_tests={args.no_tests})")
    print(f"Text files included: {len(blocks)}")
    print(f"Number of parts: {total_parts} (limit ~{max_kb:.0f} KiB per file)\n")

    total_size = 0
    dash_line = "-" * 88
    for number, (part_files, content) in enumerate(parts, start=1):
        filename = f"snapshot_{number:03d}.txt"
        status_block = f"{status}\n{'=' * 88}\n" if number == 1 else ""
        header = (
                status_block
                + f"PROJECT SNAPSHOT — PART {number}/{total_parts}\n"
                  f"Project: {root.name}\n"
                  f"Files in this part ({len(part_files)}): {', '.join(part_files)}\n"
                  f"{dash_line}\n"
        )
        footer = (
            f"\n{dash_line}\n"
            f"END OF PART {number}/{total_parts}\n"
        )
        destination = output / filename
        destination.write_text(header + content + footer, encoding="utf-8", newline="\n")
        size = destination.stat().st_size
        total_size += size

        print(f"  [{number:02d}/{total_parts:02d}] {filename}: {size / 1024:.1f} KiB ({len(part_files)} files)")
        index_lines.append(f"\n--- {filename} ({size / 1024:.1f} KiB) ---")
        for pf in part_files:
            index_lines.append(f"  - {pf}")

    (output / "README.txt").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    (output / "STATUS.md").write_text(status, encoding="utf-8")

    if unreadable:
        report = output / "unreadable_files.txt"
        report.write_text("\n".join(unreadable), encoding="utf-8")
        print(f"\nCould not read files: {len(unreadable)} (see {report})")

    est_tokens = int(total_size / 3.5)
    print(f"\nDone! Snapshot folder: {output}")
    print(f"Total size: {total_size / 1024:.1f} KiB (~{est_tokens // 1000}k tokens)")
    if est_tokens > SAFE_CONTEXT_TOKENS:
        print(
            f"⚠️  Warning: the size (~{est_tokens // 1000}k tokens) exceeds the safe chat window "
            f"(~{SAFE_CONTEXT_TOKENS // 1000}k).\n"
            f"   To keep all the code in the AI's memory, use: python make_snapshot.py --no-tests"
        )
    else:
        print("✅ The snapshot fits entirely into the AI context window without evicting the earlier parts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
