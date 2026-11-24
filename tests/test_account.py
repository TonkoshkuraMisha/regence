# --- FILE: tests/test_account.py ---
"""Account (tasks 17.5, 23.1): export of own data, account deletion with a grace period, restoring, anonymisation."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from src.core.config import settings
from src.core.security import get_password_hash
from src.models.game import Game, GameStatus
from src.models.personality import BotPersonality
from src.models.social import DirectMessage, Follow, Post
from src.models.user import User
from src.services import account
from src.services import direct_messages as dm

API = "/api/v1/account"
PASSWORD = "secret-pass-1"


async def with_password(db_session, user: User) -> None:
    user.hashed_password = get_password_hash(PASSWORD)
    await db_session.commit()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def me(client, token):
    return client.get("/api/v1/profile/me", headers=auth(token)).json()


def test_export_contains_profile_games_and_personalities(client, token_user_1):
    client.post("/api/v1/bots/personalities", headers=auth(token_user_1),
                json={"name": "Gambit", "config": {}})
    response = client.get(f"{API}/export", headers=auth(token_user_1))
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    data = response.json()
    assert data["format"] == 1 and data["profile"]["username"] == me(client, token_user_1)["username"]
    assert [p["name"] for p in data["personalities"]] == ["Gambit"]
    for key in ("games", "lessons", "puzzle_themes", "puzzle_attempts", "personal_puzzles", "tournaments"):
        assert isinstance(data[key], list)


def test_export_requires_login(client):
    assert client.get(f"{API}/export").status_code == 401


def _login(client, name: str):
    return client.post("/api/v1/auth/login", data={"username": name, "password": PASSWORD})


async def test_delete_closes_the_account_and_login_offers_restore(client, db_session, test_user_1, token_user_1):
    await with_password(db_session, test_user_1)
    user_id, name = test_user_1.id, test_user_1.username

    wrong = client.post(f"{API}/delete", headers=auth(token_user_1), json={"password": "nope-nope"})
    assert wrong.status_code == 400 and wrong.json()["detail"]["code"] == "wrong_current_password"

    response = client.post(f"{API}/delete", headers=auth(token_user_1), json={"password": PASSWORD})
    assert response.status_code == 200
    when = datetime.fromisoformat(response.json()["delete_after"])
    expected = datetime.now(UTC) + timedelta(days=settings.ACCOUNT_DELETION_GRACE_DAYS)
    assert abs((when - expected).total_seconds()) < 60

    # Closed at once: the token is revoked, the profile and the search hide the player, the data is still there.
    assert client.get("/api/v1/profile/me", headers=auth(token_user_1)).status_code == 401
    assert client.get(f"/api/v1/profile/{name}").status_code == 404
    db_session.expire_all()
    user = await db_session.get(User, user_id)
    assert user.username == name and user.deleted_at is None and user.deletion_requested_at is not None

    # Logging in tells the date; restoring with the same password logs in and cancels the deletion.
    login = _login(client, name)
    assert login.status_code == 403
    assert login.json()["detail"]["code"] == "account_deletion_pending"
    assert login.json()["detail"]["params"]["delete_after"] == when.date().isoformat()
    wrong_restore = client.post("/api/v1/auth/restore", data={"username": name, "password": "nope-nope"})
    assert wrong_restore.status_code == 401
    restored = client.post("/api/v1/auth/restore", data={"username": name, "password": PASSWORD})
    assert restored.status_code == 200
    assert client.get("/api/v1/profile/me", headers=auth(restored.json()["access_token"])).status_code == 200
    assert client.get(f"/api/v1/profile/{name}").status_code == 200
    assert _login(client, name).status_code == 200


async def test_purge_anonymises_after_the_grace_period(client, db_session, test_user_1, test_user_2, token_user_1):
    await with_password(db_session, test_user_1)
    user_id, other = test_user_1.id, test_user_2.id
    name = test_user_1.username
    assert client.put("/api/v1/conferences/me", headers=auth(token_user_1), json={"country": "UA"}).status_code == 200
    client.post("/api/v1/bots/personalities", headers=auth(token_user_1), json={"name": "Gambit", "config": {}})
    db_session.add_all([
        Game(white_player_id=user_id, black_player_id=other, status=GameStatus.COMPLETED, result="1-0"),
        Follow(follower_id=other, followee_id=user_id),
        DirectMessage(pair_key=dm.pair_key(user_id, other), sender_id=other, recipient_id=user_id, body="hi"),
        Post(author_id=user_id, body="my game"),
    ])
    await db_session.commit()
    assert client.post(f"{API}/delete", headers=auth(token_user_1), json={"password": PASSWORD}).status_code == 200

    # Inside the grace period nothing is erased.
    assert await account.purge_due(db_session) == 0
    later = datetime.now(UTC) + timedelta(days=settings.ACCOUNT_DELETION_GRACE_DAYS, minutes=1)
    assert await account.purge_due(db_session, now=later) == 1

    db_session.expire_all()
    user = await db_session.get(User, user_id)
    assert user.username == f"deleted_{user_id}" and user.deleted_at is not None and user.email is None
    assert user.country is None                                                 # country from the profile — personal data
    for model, column in ((BotPersonality, BotPersonality.owner_id), (Follow, Follow.followee_id),
                          (DirectMessage, DirectMessage.recipient_id), (Post, Post.author_id)):
        assert await db_session.scalar(select(func.count()).select_from(model).where(column == user_id)) == 0
    # The game stays with the opponent.
    assert await db_session.scalar(select(func.count(Game.id)).where(Game.white_player_id == user_id)) == 1
    # The old name cannot log in or restore; the anonymous profile is not public.
    assert _login(client, name).status_code == 401
    assert client.post("/api/v1/auth/restore", data={"username": name, "password": PASSWORD}).status_code == 401
    assert client.get(f"/api/v1/profile/deleted_{user_id}").status_code == 404
    board = client.get("/api/v1/profile/leaderboard").json()
    assert all(row["username"] != f"deleted_{user_id}" for row in board)
    # A second run finds nothing left to do.
    assert await account.purge_due(db_session, now=later) == 0


async def test_cannot_delete_during_a_game(client, db_session, test_user_1, token_user_1, token_user_2):
    await with_password(db_session, test_user_1)
    user_id, other = me(client, token_user_1)["id"], me(client, token_user_2)["id"]
    db_session.add(Game(white_player_id=user_id, black_player_id=other, status=GameStatus.IN_PROGRESS))
    await db_session.commit()
    response = client.post(f"{API}/delete", headers=auth(token_user_1), json={"password": PASSWORD})
    assert response.status_code == 409 and response.json()["detail"]["code"] == "account_in_game"
