# --- FILE: tests/test_error_codes.py ---
"""
Errors for the client are codes, not texts (task 11.0b).

* The src/core/errors.py registry matches the serverErrors section in the three client catalogs: the same codes
  and the same template parameters. A new code without a translation (or a translation without a code) fails this test.
* Every code the server emits anywhere is in the registry, and every registry code is used somewhere.
* Response formats: HTTP - {"detail": {"code", "params", "message"}}, 422 - a list without echoing submitted values,
  429 - with a retry_after parameter, WebSocket - an error event with a code.
"""

import ast
import pathlib
import re
import string

import pytest

from src.core.errors import (
    ERROR_MESSAGES,
    ApiError,
    DomainError,
    error_payload,
    template_params,
    validation_error,
    validation_error_items,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
CATALOGS = ROOT / "frontend" / "src" / "i18n" / "messages"
LANGUAGES = ("en", "uk")


def _catalog_section(language: str, section: str) -> dict[str, str]:
    text = (CATALOGS / f"{language}.ts").read_text(encoding="utf-8")
    match = re.search(rf"^    {section}: \{{\n(.*?)^    \}},$", text, re.M | re.S)
    assert match, f"{language}.ts: no section {section}"
    entries = {}
    for key, value in re.findall(r"^        (\w+): '((?:[^'\\]|\\.)*)',$", match.group(1), re.M):
        entries[key] = value.replace("\\'", "'")
    return entries


def _placeholders(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


# --- registry and catalogs ------------------------------------------------------------------------------------

@pytest.mark.parametrize("language", LANGUAGES)
def test_catalog_has_exactly_the_registry_codes(language):
    assert set(_catalog_section(language, "serverErrors")) == set(ERROR_MESSAGES)


@pytest.mark.parametrize("language", LANGUAGES)
def test_catalog_texts_use_the_same_params_as_the_registry(language):
    catalog = _catalog_section(language, "serverErrors")
    for code in ERROR_MESSAGES:
        assert _placeholders(catalog[code]) == template_params(code), f"{language}: {code}"


def _codes_used_in_source() -> set[str]:
    """Codes from calls that create errors for the client, and from the "code"/reason fields of responses."""
    positional = {
        "ApiError": 1, "error_payload": 0, "validation_error": 0, "DomainError": 0, "DomainValueError": 0,
        "MatchmakingError": 0, "GameNotFinishedError": 0, "GameDataNotFoundError": 0,
        "InvalidStartPositionError": 0, "PuzzleError": 0, "GameImportError": 0, "error": 0, "enforce_rate_limit": 4,
        "ensure_below_limit": 4,
        # Kid mode and secret checks (task 23.1): the refusal code is an argument.
        "refuse_kid_mode": 0, "ensure_not_kid": 1, "_check_secret": 3,
    }
    used: set[str] = set()
    for path in (ROOT / "src").rglob("*.py"):
        if path.name == "errors.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
                index = positional.get(name)
                if name == "error" and not (isinstance(func, ast.Attribute) and getattr(func.value, "id", "") == "ctx"):
                    index = None  # logger.error etc. - not an error for the client
                if index is not None and len(node.args) > index:
                    arg = node.args[index]
                    # ctx.error(result.get("code", "fallback_code")) - the fallback code is also sent to the client.
                    if (isinstance(arg, ast.Call) and getattr(arg.func, "attr", "") == "get" and len(arg.args) == 2
                            and getattr(arg.args[0], "value", None) == "code"):
                        arg = arg.args[1]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        used.add(arg.value)
                for keyword in node.keywords:
                    if keyword.arg == "reason" and isinstance(keyword.value, ast.Constant) and name == "SkippedPersonality":
                        used.add(keyword.value.value)
                    # rate_limit(..., code="...") - its own 429 code for endpoints without an engine.
                    if keyword.arg == "code" and isinstance(keyword.value, ast.Constant) and name == "rate_limit":
                        used.add(keyword.value.value)
            if isinstance(node, ast.FunctionDef) and node.name == "rate_limit":
                # The default 429 code is the value of the code parameter.
                for arg, default in zip(reversed(node.args.args), reversed(node.args.defaults), strict=False):
                    if arg.arg == "code" and isinstance(default, ast.Constant):
                        used.add(default.value)
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values, strict=True):
                    if getattr(key, "value", None) == "code" and isinstance(value, ast.Constant):
                        used.add(value.value)
    return used


def test_every_code_in_source_is_registered_and_every_registered_code_is_used():
    used = _codes_used_in_source()
    assert used - set(ERROR_MESSAGES) == set(), "codes without a registry entry"
    assert set(ERROR_MESSAGES) - used == set(), "registry codes the server never emits"


# --- building errors --------------------------------------------------------------------------------------------

def test_payload_carries_code_params_and_english_message():
    assert error_payload("rating_out_of_range", rating=1500, min=1600, max=1800) == {
        "code": "rating_out_of_range",
        "params": {"rating": 1500, "min": 1600, "max": 1800},
        "message": "Your rating 1500 is outside the challenge range (1600–1800)",
    }


def test_unknown_code_and_missing_params_are_programming_errors():
    with pytest.raises(KeyError):
        error_payload("no_such_code")
    with pytest.raises(KeyError):
        error_payload("user_not_found")  # no username


def test_english_messages_contain_no_cyrillic():
    assert not [code for code, text in ERROR_MESSAGES.items() if re.search(r"[Ѐ-ӿ]", text)]


def test_domain_error_converts_to_http_with_the_same_code():
    http = DomainError("game_not_finished", game_id=7).to_http(409)
    assert isinstance(http, ApiError)
    assert http.status_code == 409
    assert http.detail == error_payload("game_not_finished", game_id=7)


def test_validation_error_items_drop_input_and_keep_params():
    items = validation_error_items([
        {"type": "string_too_short", "loc": ("body", "password"), "msg": "too short",
         "input": "secret", "ctx": {"min_length": 8}},
        {"type": "username_mixed_scripts", "loc": ("body", "username"), "msg": "x", "input": "Мorphy"},
    ])
    assert items == [
        {"type": "string_too_short", "loc": ["body", "password"], "msg": "too short", "params": {"min_length": 8}},
        {"type": "username_mixed_scripts", "loc": ["body", "username"], "msg": "x", "params": {}},
    ]


def test_validation_error_formats_params_like_the_registry():
    error = validation_error("personality_limit", max=20)
    assert error.type == "personality_limit"
    assert error.message() == "No more than 20 opponents in the workshop — delete some"


# --- API responses ----------------------------------------------------------------------------------------------

def test_http_error_body(client):
    response = client.get("/api/v1/profile/nobody_like_this")
    assert response.status_code == 404
    assert response.json() == {"detail": error_payload("user_not_found", username="nobody_like_this")}


def test_422_has_codes_and_does_not_echo_the_password(client):
    response = client.post("/api/v1/auth/register", json={"username": "Мorphy", "password": "pw7Zq"})
    assert response.status_code == 422
    assert "pw7Zq" not in response.text and "Мorphy" not in response.text  # what was submitted is not echoed back
    by_field = {item["loc"][-1]: item for item in response.json()["detail"]}
    assert by_field["username"]["type"] == "username_mixed_scripts"
    assert by_field["password"]["type"] == "string_too_short"
    assert by_field["password"]["params"] == {"min_length": 8}


def test_429_has_retry_after_in_params_and_header(client, monkeypatch, freeze_rate_limit_window):
    from src.core.config import settings

    monkeypatch.setattr(settings, "RATE_LIMIT_REGISTER_PER_IP", 1)
    assert client.post("/api/v1/auth/register", json={"username": "first_one", "password": "secret123"}).status_code == 201
    limited = client.post("/api/v1/auth/register", json={"username": "second_one", "password": "secret123"})
    assert limited.status_code == 429
    detail = limited.json()["detail"]
    assert detail["code"] == "too_many_registrations"
    assert detail["params"]["retry_after"] == int(limited.headers["Retry-After"])


def test_login_failure_is_a_code(client):
    response = client.post("/api/v1/auth/login", data={"username": "ghost", "password": "whatever1"})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "login_failed"
