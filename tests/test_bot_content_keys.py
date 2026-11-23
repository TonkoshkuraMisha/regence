# --- FILE: tests/test_bot_content_keys.py ---
"""
Bot content reaches the client as keys (task 11.0c): every line key, archetype id and ladder reason code
the server can emit has text in the client catalog, and the catalog has nothing extra. The sameness of
the three catalogs (en/uk/ru) is checked by TypeScript and client tests; English is enough here.
"""

import ast
import pathlib
import re

from src.services.bots import BOT_INSTANCES
from src.services.bots.archetypes import ARCHETYPES
from src.services.ladder import LADDER_REASONS

ROOT = pathlib.Path(__file__).resolve().parent.parent
CATALOG = (ROOT / "frontend" / "src" / "i18n" / "messages" / "en.ts").read_text(encoding="utf-8")
COMMENT_GROUPS = ("common", "personality", *BOT_INSTANCES)
COMMENT_KEY = re.compile(rf"^(?:{'|'.join(COMMENT_GROUPS)})\.[A-Za-z][A-Za-z0-9]*$")


def _section(name: str, indent: int = 4) -> str:
    pad = " " * indent
    match = re.search(rf"^{pad}{name}: \{{\n(.*?)^{pad}\}},$", CATALOG, re.M | re.S)
    assert match, f"no section {name}"
    return match.group(1)


def _leaf_keys(block: str, indent: int) -> set[str]:
    """String keys and nested sections of block (with the given indent) as "section.key" paths."""
    keys: set[str] = set()
    pad = " " * indent
    for match in re.finditer(rf"^{pad}(\w+): (\{{\n(.*?)^{pad}\}},|'(?:[^'\\]|\\.)*',)$", block, re.M | re.S):
        name, nested = match.group(1), match.group(3)
        if nested is None:
            keys.add(name)
        else:
            keys.update(f"{name}.{inner}" for inner in _leaf_keys(nested, indent + 4))
    return keys


def _server_comment_keys() -> set[str]:
    keys: set[str] = set()
    for path in (ROOT / "src" / "services" / "bots").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and COMMENT_KEY.match(node.value):
                keys.add(node.value)
    keys.update(f"book.{bot_id}" for bot_id in BOT_INSTANCES)  # opening-book moves from JSON
    return keys


def test_every_bot_comment_key_has_a_text_and_no_text_is_orphaned():
    catalog = _leaf_keys(_section("botComments"), 8)
    server = _server_comment_keys()
    assert server - catalog == set(), "keys without text in the catalog"
    assert catalog - server == set(), "texts the server never emits"


def test_book_texts_take_the_number_of_games():
    for bot_id in BOT_INSTANCES:
        line = re.search(rf"^            {bot_id}: '(.*)',$", _section("book", 8), re.M)
        assert line and "{games}" in line.group(1), bot_id


def test_archetype_ids_match_the_catalog():
    names = set(re.findall(r"^        (\w+): \{$", _section("archetypes"), re.M))
    assert names == {a.id for a in ARCHETYPES}


def test_ladder_reasons_match_the_catalog():
    reasons = set(re.findall(r"^            (\w+): ", _section("reasons", 8), re.M))
    assert reasons == set(LADDER_REASONS)


def test_style_notes_are_keys_not_text():
    """No style note is left as plain text: everything the style evaluator can return is a key."""
    from src.services.bots.personality import BotPersonalityConfig, PersonalityBot, default_comment_for

    for bot in BOT_INSTANCES.values():
        assert COMMENT_KEY.match(bot.default_comment), bot.bot_id
    for aggression in (-100, 0, 100):
        assert COMMENT_KEY.match(default_comment_for(BotPersonalityConfig(aggression=aggression)))
    assert PersonalityBot(BotPersonalityConfig()).default_comment.startswith("personality.")
