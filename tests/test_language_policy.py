"""
Language policy guard (owner decision of 23.11.2026, see CLAUDE.md "Language policy").

The project has two languages only: English (primary) and Ukrainian. Russian must not appear anywhere.
Two checks over the files tracked by git:

* Russian-only letters (yo, hard sign, yery, e-reversed) must not occur in any tracked text file - the letters are
  not used in Ukrainian, so their presence means Russian text;
* code files (``*.py``, ``*.ts``, ``*.tsx``) contain no Cyrillic at all, except the files that legitimately hold
  Ukrainian text (CODE_FILES_WITH_UKRAINIAN): the Ukrainian catalog, the mail templates, test fixtures that check Ukrainian
  behaviour.

The test source itself is written with ``\\u`` escapes, so it contains no Cyrillic.
"""

import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Russian-only letters: yo, hard sign, yery, e-reversed (both cases) - none of them exists in Ukrainian.
RUSSIAN_ONLY = re.compile("[\u0401\u0451\u042a\u044a\u042b\u044b\u042d\u044d]")
CYRILLIC = re.compile("[\u0400-\u04ff]")

TEXT_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".json", ".md", ".txt", ".yml", ".yaml", ".toml", ".html", ".css", ".conf",
    ".inc", ".ini", ".cfg", ".sh", ".example", ".mako",
}
CODE_SUFFIXES = {".py", ".ts", ".tsx"}

# Code files that hold Ukrainian text on purpose (an exact path or a path prefix).
CODE_FILES_WITH_UKRAINIAN = (
    "frontend/src/i18n/messages/uk.ts",   # the Ukrainian catalog
    "frontend/src/i18n/messages/glossary.ts",  # chess glossary: the Ukrainian terms
    "frontend/src/i18n/messages/languageNames.ts",  # native language name
    "frontend/src/content/",  # lessons and course data (en + uk)
    "src/services/mailer.py",  # Ukrainian e-mail templates
    "tests/",  # fixtures of Ukrainian behaviour (usernames, civility filter)
    "frontend/src/__tests__/",
    "frontend/e2e/",
    "scripts/dev/",
    "src/schemas/user.py",
)

# This file is checked only for Russian-only letters through the whole repository scan.


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def _read(path: str) -> str | None:
    file = PROJECT_ROOT / path
    if file.suffix not in TEXT_SUFFIXES or not file.is_file():
        return None
    try:
        return file.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def _is_allowed_ukrainian(path: str) -> bool:
    return path.startswith(CODE_FILES_WITH_UKRAINIAN) or "/__tests__/" in path or path.endswith((".test.ts", ".test.tsx"))


def test_no_russian_only_letters_anywhere() -> None:
    offenders = []
    for path in _tracked_files():
        text = _read(path)
        if text is not None and RUSSIAN_ONLY.search(text):
            offenders.append(path)
    assert not offenders, f"Russian text found (owner decision of 23.11.2026): {offenders}"


def test_no_cyrillic_in_code_files_except_ukrainian_ones() -> None:
    offenders = []
    for path in _tracked_files():
        if Path(path).suffix not in CODE_SUFFIXES or _is_allowed_ukrainian(path):
            continue
        text = _read(path)
        if text is not None and CYRILLIC.search(text):
            offenders.append(path)
    assert not offenders, f"Cyrillic in code outside the Ukrainian files: {offenders}"


def test_language_lists_are_en_uk_only() -> None:
    core = (PROJECT_ROOT / "frontend" / "src" / "i18n" / "core.ts").read_text(encoding="utf-8")
    assert "['en', 'uk'] as const" in core
    mailer = (PROJECT_ROOT / "src" / "services" / "mailer.py").read_text(encoding="utf-8")
    assert 'LANGUAGES: tuple[Language, ...] = ("en", "uk")' in mailer
