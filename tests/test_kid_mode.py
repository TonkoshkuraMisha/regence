"""
Kid mode (task 23.1, src/services/kid_mode.py): registration under 16 with a guardian, turning the mode on and off, and
what it closes - direct messages, the feed and the study room chat. The game chat is checked in test_ws_actions.py.
"""

import pytest
from sqlalchemy import select

from src.core.errors import ApiError, DomainError
from src.core.security import get_password_hash, verify_password
from src.models.social import Post
from src.models.user import User
from src.services import kid_mode, legal

PASSWORD = "secret-pass-1"
GUARDIAN = "4711"
REGISTER = "/api/v1/auth/register"
KID_MODE = "/api/v1/account/kid-mode"


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def make_kid(db_session, user: User, guardian_code: str | None = None) -> None:
    user.hashed_password = get_password_hash(PASSWORD)
    kid_mode.enable(user, guardian_code)
    await db_session.commit()


# --- Pure rules -------------------------------------------------------------------------------------------------------

def test_free_chat_is_refused_when_any_player_is_a_kid():
    adult, kid = User(kid_mode=False), User(kid_mode=True)
    assert kid_mode.free_chat_refusal([adult, None]) is None
    assert kid_mode.free_chat_refusal([adult, kid]) == "chat_kid_mode"


def test_guardian_code_is_stored_as_a_hash_and_forgotten_on_disable():
    user = User(kid_mode=False, kid_guardian_hash=None)
    kid_mode.enable(user, GUARDIAN)
    assert user.kid_mode and user.kid_guardian_hash != GUARDIAN and verify_password(GUARDIAN, user.kid_guardian_hash)
    kid_mode.disable(user)
    assert not user.kid_mode and user.kid_guardian_hash is None


def test_under_16_needs_consent_and_code():
    legal.require_guardian(False, False, None)
    legal.require_guardian(True, True, GUARDIAN)
    for consent, code in ((False, GUARDIAN), (True, None)):
        with pytest.raises(ApiError):
            legal.require_guardian(True, consent, code)


# --- Registration -----------------------------------------------------------------------------------------------------

def test_under_16_without_a_guardian_is_refused(client):
    res = client.post(REGISTER, json={"username": "Young", "password": "secret123", "under_16": True})
    assert res.status_code == 400 and res.json()["detail"]["code"] == "guardian_consent_required"


async def test_under_16_with_a_guardian_starts_in_kid_mode(client, db_session):
    res = client.post(REGISTER, json={"username": "Young", "password": "secret123", "under_16": True,
                                      "guardian_consent": True, "guardian_code": GUARDIAN})
    assert res.status_code == 201
    user = (await db_session.execute(select(User).where(User.username == "Young"))).scalar_one()
    assert user.kid_mode and verify_password(GUARDIAN, user.kid_guardian_hash)


# --- Turning it on and off --------------------------------------------------------------------------------------------

async def test_password_turns_kid_mode_on_and_off(client, db_session, test_user_1, token_user_1):
    test_user_1.hashed_password = get_password_hash(PASSWORD)
    await db_session.commit()
    wrong = client.post(KID_MODE, headers=auth(token_user_1), json={"enabled": True, "password": "nope-nope"})
    assert wrong.status_code == 400 and wrong.json()["detail"]["code"] == "wrong_current_password"
    on = client.post(KID_MODE, headers=auth(token_user_1), json={"enabled": True, "password": PASSWORD})
    assert on.json() == {"kid_mode": True, "kid_guardian_code": False}
    me = client.get("/api/v1/profile/me", headers=auth(token_user_1)).json()
    assert me["kid_mode"] is True and me["kid_guardian_code"] is False
    off = client.post(KID_MODE, headers=auth(token_user_1), json={"enabled": False, "password": PASSWORD})
    assert off.json() == {"kid_mode": False, "kid_guardian_code": False}


async def test_only_the_guardian_code_turns_it_off(client, db_session, test_user_1, token_user_1):
    await make_kid(db_session, test_user_1, GUARDIAN)
    user_id = test_user_1.id
    by_password = client.post(KID_MODE, headers=auth(token_user_1), json={"enabled": False, "password": PASSWORD})
    assert by_password.status_code == 400 and by_password.json()["detail"]["code"] == "guardian_code_wrong"
    # Turning it "on" again with the password does not replace the guardian's code.
    client.post(KID_MODE, headers=auth(token_user_1), json={"enabled": True, "password": PASSWORD,
                                                             "guardian_code": "0000"})
    db_session.expire_all()
    assert verify_password(GUARDIAN, (await db_session.get(User, user_id)).kid_guardian_hash)
    off = client.post(KID_MODE, headers=auth(token_user_1), json={"enabled": False, "guardian_code": GUARDIAN})
    assert off.status_code == 200 and off.json()["kid_mode"] is False


# --- What it closes ---------------------------------------------------------------------------------------------------

async def test_messages_are_closed_both_ways(client, db_session, test_user_1, test_user_2, token_user_1, token_user_2):
    await make_kid(db_session, test_user_1)
    listing = client.get("/api/v1/messages", headers=auth(token_user_1))
    assert listing.status_code == 403 and listing.json()["detail"]["code"] == "dm_kid_mode"
    to_kid = client.post(f"/api/v1/messages/with/{test_user_1.username}", headers=auth(token_user_2),
                         json={"body": "hello"})
    assert to_kid.status_code == 403 and to_kid.json()["detail"]["code"] == "dm_closed"


async def test_feed_is_closed_and_a_kids_posts_stay_private(client, db_session, test_user_1, token_user_1):
    db_session.add(Post(author_id=test_user_1.id, body="before kid mode"))
    await make_kid(db_session, test_user_1)
    closed = client.get("/api/v1/feed", headers=auth(token_user_1))
    assert closed.status_code == 403 and closed.json()["detail"]["code"] == "feed_kid_mode"
    post = client.post("/api/v1/feed", headers=auth(token_user_1), json={"body": "hi"})
    assert post.status_code == 403
    # A guest does not see the kid's earlier posts in the profile feed.
    assert client.get(f"/api/v1/feed/user/{test_user_1.username}").json()["posts"] == []
    public = client.get(f"/api/v1/profile/{test_user_1.username}").json()
    assert public["kid_mode"] is True


async def test_study_room_chat_is_closed_but_the_board_is_open(client, db_session, test_user_1, test_user_2,
                                                               token_user_1, token_user_2):
    code = client.post("/api/v1/study", headers=auth(token_user_2)).json()["code"]
    assert client.post(f"/api/v1/study/{code}/chat", headers=auth(token_user_2), json={"text": "welcome"}).status_code == 200
    await make_kid(db_session, test_user_1)
    room = client.get(f"/api/v1/study/{code}", headers=auth(token_user_1))
    assert room.status_code == 200 and room.json()["chat"] == []
    said = client.post(f"/api/v1/study/{code}/chat", headers=auth(token_user_1), json={"text": "hi"})
    assert said.status_code == 403 and said.json()["detail"]["code"] == "chat_kid_mode"


def test_ensure_not_kid_raises_the_given_code():
    with pytest.raises(DomainError) as caught:
        kid_mode.ensure_not_kid(User(kid_mode=True), "feed_kid_mode")
    assert caught.value.code == "feed_kid_mode"
    kid_mode.ensure_not_kid(None, "feed_kid_mode")
