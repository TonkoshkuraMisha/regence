# --- FILE: tests/test_no_russian_in_api.py ---
"""
The server does not send Russian text to the user (task 11.0c): the client builds texts in three languages from catalogues,
the server sends codes, keys and parameters.

* src sources: no string literal with Cyrillic outside docstrings, OpenAPI field descriptions (description=),
  logs and print - those are developer texts, written in English. An exception is the regular expressions of
  the name rules, which do allow Cyrillic.
* Exception - mail texts (src/services/mailer.py, task 17.5): the mail is read in a mail client, there are no frontend
  catalogues there, so it is built on the server in the player's language; all three languages live there.
* Data that the server returns as is (bot opening books) - without Cyrillic.
* Responses of the key bot and ladder endpoints - without Cyrillic.
"""

import ast
import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CYRILLIC = re.compile(r"[Ѐ-ӿ]")
LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical"}
# Player names may be Cyrillic: the name rule lists the letters of the alphabet.
ALLOWED = {
    ("src/schemas/user.py", "[A-Za-z0-9А-Яа-яЁё_-]+"),
    ("src/schemas/user.py", "[А-Яа-яЁё]"),
}


def _developer_text_nodes(tree: ast.AST) -> set[int]:
    skip: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and body \
                and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            skip.add(id(body[0].value))
        if isinstance(node, ast.Call):
            func = node.func
            developer_call = (isinstance(func, ast.Attribute) and func.attr in LOG_METHODS) or (
                isinstance(func, ast.Name) and func.id == "print")
            parts = list(node.args) if developer_call else []
            parts += [kw.value for kw in node.keywords if kw.arg == "description"]
            for part in parts:
                skip.update(id(inner) for inner in ast.walk(part))
    return skip


def _user_facing_cyrillic(path: pathlib.Path) -> list[str]:
    rel = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.name
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip = _developer_text_nodes(tree)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and CYRILLIC.search(node.value) \
                and id(node) not in skip and (rel, node.value) not in ALLOWED:
            found.append(f"{rel}:{node.lineno}: {node.value[:80]}")
    return found


# Files where human-facing texts in three languages live on the server out of necessity (see the module description).
ALLOWED_FILES = {"src/services/mailer.py"}


def test_server_source_has_no_user_facing_russian():
    found = [line for path in sorted((ROOT / "src").rglob("*.py"))
             if path.relative_to(ROOT).as_posix() not in ALLOWED_FILES
             for line in _user_facing_cyrillic(path)]
    assert found == [], "\n" + "\n".join(found)


def test_guard_sees_strings_but_not_developer_text(tmp_path):
    probe = tmp_path / "probe.py"
    probe.write_text(
        '"""\u041c\u043e\u0434\u0443\u043b\u044c."""\n'
        'import logging\n'
        'logger = logging.getLogger(__name__)\n'
        'def f(x=None):\n'
        '    """\u0424\u0443\u043d\u043a\u0446\u0438\u044f."""\n'
        '    logger.warning("\u041b\u043e\u0433 %s", x)\n'
        '    return {"comment": "\u0420\u0435\u043f\u043b\u0438\u043a\u0430"}\n',
        encoding="utf-8",
    )
    assert [line.split(": ", 1)[1] for line in _user_facing_cyrillic(probe)] == ["\u0420\u0435\u043f\u043b\u0438\u043a\u0430"]


def test_opening_books_have_no_russian():
    for book in sorted((ROOT / "src" / "services" / "bots" / "books").glob("*.json")):
        assert not CYRILLIC.search(book.read_text(encoding="utf-8")), book.name


def _assert_no_cyrillic(payload) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    assert not CYRILLIC.search(text), text[:500]


@pytest.mark.parametrize("url", ["/api/v1/bots/catalog", "/api/v1/bots/list"])
def test_bot_catalogs_have_no_russian(client, url):
    response = client.get(url)
    assert response.status_code == 200
    _assert_no_cyrillic(response.json())


@pytest.mark.parametrize("bot_id", ["philidor", "labourdonnais", "staunton", "anderssen", "morphy", "paulsen", "zukertort"])
def test_bot_moves_answer_with_comment_keys(client, monkeypatch, bot_id):
    from src.services.bots import base as bots_base

    monkeypatch.setattr(bots_base, "analyse_with_stockfish", lambda **kwargs: {})
    for fen in (
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",  # book move
        "r1bq1rk1/pp3ppp/2n2n2/2bpp3/8/2NP1NP1/PPP1PPBP/R1BQ1RK1 w - - 0 9",  # style move
    ):
        response = client.post("/api/v1/bots/move", json={"bot_id": bot_id, "fen": fen})
        assert response.status_code == 200, response.text
        body = response.json()
        _assert_no_cyrillic(body)
        assert set(body["comment"]) == {"key", "params"}


def test_custom_bot_move_answers_with_a_comment_key(client, monkeypatch):
    from src.services.bots import base as bots_base

    monkeypatch.setattr(bots_base, "analyse_with_stockfish", lambda **kwargs: {})
    response = client.post("/api/v1/bots/custom-move", json={
        "fen": "r1bq1rk1/pp3ppp/2n2n2/2bpp3/8/2NP1NP1/PPP1PPBP/R1BQ1RK1 w - - 0 9",
    })
    assert response.status_code == 200, response.text
    _assert_no_cyrillic(response.json())
    assert response.json()["comment"]["key"].startswith("personality.")


def test_mail_templates_cover_every_language():
    from src.services.mailer import LANGUAGES, TEMPLATES

    for kind, by_language in TEMPLATES.items():
        assert set(by_language) == set(LANGUAGES), kind
        for subject, body in by_language.values():
            assert subject and "{link}" in body and "{hours}" in body and "{username}" in body
