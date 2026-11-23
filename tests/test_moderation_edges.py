# --- FILE: tests/test_moderation_edges.py ---
"""Moderation: internal-function rejections: bad complaint kind/reason, translation suggestions, repeat appeal, decisions."""

import pytest

from src.core.errors import DomainError
from src.models.user import User
from src.services import moderation


async def _code(awaitable) -> str:
    with pytest.raises(DomainError) as error:
        await awaitable
    return error.value.code


async def test_report_rejects_bad_kind_reason_and_self(db_session, test_user_1, test_user_2):
    assert await _code(moderation.report(db_session, test_user_1, test_user_2, "bogus", "abuse", None)) == "report_invalid"
    assert await _code(moderation.report(db_session, test_user_1, test_user_2, "player", "bogus", None)) == "report_invalid"
    assert await _code(moderation.report(db_session, test_user_1, test_user_1, "player", "abuse", None)) == "report_self"


async def test_translation_suggestion_rules(db_session, test_user_1):
    args = (db_session, test_user_1, "en", "menu.play", "Play", "Start", None)
    assert await _code(moderation.suggest_translation(*args)) == "translation_helper_off"
    test_user_1.translation_helper = True
    await db_session.commit()
    for bad in (("xx", "menu.play", "Play", "Start", None), ("en", "", "Play", "Start", None),
                ("en", "menu.play", "Play", "   ", None)):
        assert await _code(moderation.suggest_translation(db_session, test_user_1, *bad)) == "report_invalid"


async def test_appeal_needs_a_flag_and_only_one_is_open(db_session, test_user_1):
    assert await _code(moderation.appeal(db_session, test_user_1, None)) == "appeal_not_flagged"
    test_user_1.is_cheater = True
    await db_session.commit()
    await moderation.appeal(db_session, test_user_1, "unfair")
    assert await _code(moderation.appeal(db_session, test_user_1, None)) == "report_duplicate"


async def test_resolve_refusals(db_session, test_user_1):
    moderator = User(username="mod2", hashed_password="x", is_moderator=True)
    db_session.add(moderator)
    await db_session.commit()
    assert await _code(moderation.resolve(db_session, test_user_1, 1, "dismiss")) == "moderator_only"
    assert await _code(moderation.resolve(db_session, moderator, 1, "bogus")) == "report_invalid"
    assert await _code(moderation.resolve(db_session, moderator, 999_999, "dismiss")) == "report_not_found"


@pytest.mark.parametrize("subject", ["", "msg", "dm:abc", "unknown:5"])
async def test_parse_subject_rejects_bad_links(subject):
    with pytest.raises(DomainError) as error:
        moderation._parse_subject(subject)
    assert error.value.code == "report_invalid"


async def test_missing_text_is_not_found_and_decision_is_harmless(db_session):
    assert await _code(moderation.load_text(db_session, "post:999999")) == "report_not_found"
    assert await _code(moderation.load_text(db_session, "comment:999999")) == "report_not_found"
    await moderation._apply_to_text(db_session, "post:999999", "hide")  # the text was deleted by its author; nothing fails
