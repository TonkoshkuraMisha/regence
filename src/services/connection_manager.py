# --- FILE: src/services/connection_manager.py ---
"""
WebSocket connection manager, correct with several workers (processes) and tabs.

State that must be shared by all workers is kept in Redis:
- presence: each connection is an element of the sorted set `presence:user:{uid}` with the mark of the
  last heartbeat. A player is considered offline only when there are no live connections on any
  worker; entries of a crashed worker go stale after PRESENCE_STALE_MS;
- game spectators: `game:{gid}:spectators` and the reverse index `user:{uid}:spectating`.

Delivery: a message is sent at once to the user's local sockets and is always published
to the channel `user:{uid}` with the id of the sending worker. The other workers deliver it to their
tabs of this user, the sender skips its own message (no duplicates).
"""

import asyncio
import json
import logging
import time
import uuid

from fastapi import WebSocket

from src.core.instance import WORKER_ID
from src.db.redis import redis_client

logger = logging.getLogger(__name__)

# How often the process refreshes the presence marks of its connections in Redis.
PRESENCE_HEARTBEAT_S = 10
# A mark older than this (three missed heartbeats with a margin) means the connection is considered dead; the key itself
# presence:user:{uid} lives twice as long and is extended by every heartbeat.
PRESENCE_STALE_MS = 35_000

# The "tokens revoked" event and the WebSocket close code by which the client understands it must sign in again.
SESSION_REVOKED_EVENT = "session_revoked"
WS_CLOSE_SESSION_REVOKED = 1008


def _is_session_revoked(raw: str) -> bool:
    """Whether the message text is a session_revoked event (coming from another worker)."""
    if SESSION_REVOKED_EVENT not in raw:  # cheap filter before JSON parsing
        return False
    try:
        return json.loads(raw).get("event") == SESSION_REVOKED_EVENT
    except (ValueError, AttributeError):
        return False


# Lifetime of spectator records (6 hours): insurance against stuck records if a spectator vanished without disconnecting.
SPECTATING_TTL_S = 6 * 60 * 60


def _presence_key(uid: int) -> str:
    return f"presence:user:{uid}"


def _spectators_key(gid: int) -> str:
    return f"game:{gid}:spectators"


def _spectating_key(uid: int) -> str:
    return f"user:{uid}:spectating"


def _now_ms() -> int:
    return int(time.time() * 1000)


class ConnectionManager:
    """
    WebSocket connections of this process and the state shared by all processes in Redis: player presence, spectators,
    message delivery (details in the module description).
    """
    def __init__(self):
        self.worker_id = WORKER_ID
        # One (any open) connection of the player on this worker; all their tabs are in _user_sockets.
        self.active_connections: dict[int, WebSocket] = {}
        self._user_sockets: dict[int, set[WebSocket]] = {}
        # websocket -> (user_id, connection_id in the Redis presence)
        self._connections: dict[WebSocket, tuple[int, str]] = {}
        self.redis = redis_client
        self.pubsub = self.redis.pubsub()
        self._listener_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None

    # ------------------------------------------------------------------ background tasks

    def _ensure_background_tasks(self) -> None:
        """
        Starts (or restarts, if they finished) the pub/sub listener and the presence heartbeat. Called on
        every new connection: the tasks are created lazily, when a running event loop already exists.
        """
        try:
            if self._listener_task is None or self._listener_task.done():
                self._listener_task = asyncio.create_task(self._listen_pubsub())
            if self._heartbeat_task is None or self._heartbeat_task.done():
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        except RuntimeError:
            pass

    async def _heartbeat_loop(self):
        """Refreshes the presence marks of all local connections while they are open."""
        while True:
            try:
                await asyncio.sleep(PRESENCE_HEARTBEAT_S)
                now = _now_ms()
                for uid, conn_id in list(self._connections.values()):
                    await self.redis.zadd(_presence_key(uid), {conn_id: now})
                    await self.redis.expire(_presence_key(uid), PRESENCE_STALE_MS // 1000 * 2)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Presence heartbeat failed: %s", exc)

    async def _listen_pubsub(self):
        """Delivers to local sockets messages published by other workers."""
        while True:
            try:
                if not getattr(self.pubsub, "subscribed", False):
                    await asyncio.sleep(0.25)
                    continue

                message = await self.pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not message or message.get("type") != "message":
                    continue
                channel = str(message.get("channel", ""))
                if not channel.startswith("user:"):
                    continue
                raw = self._unwrap_envelope(str(message.get("data", "")))
                if raw is not None:
                    await self._on_remote_message(int(channel.split(":")[1]), raw)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.debug("PubSub listener loop warning: %s", e)
                await asyncio.sleep(0.5)

    async def _on_remote_message(self, uid: int, raw: str) -> None:
        """A message for a user, published by another worker."""
        await self._deliver_local(uid, raw)
        if _is_session_revoked(raw):
            # Tokens revoked on another worker -- close the local tabs too.
            await self._close_local_sockets(uid)

    def _unwrap_envelope(self, data: str) -> str | None:
        """Returns the payload, or None if the message was published by this same worker."""
        try:
            envelope = json.loads(data)
        except ValueError:
            return data
        if isinstance(envelope, dict) and "origin" in envelope and "data" in envelope:
            if envelope["origin"] == self.worker_id:
                return None
            return str(envelope["data"])
        return data

    # ------------------------------------------------------------------ presence

    def _has_open_sockets(self, uid: int) -> bool:
        return bool(self._user_sockets.get(uid))

    async def _presence_add(self, uid: int, conn_id: str) -> None:
        try:
            await self.redis.zadd(_presence_key(uid), {conn_id: _now_ms()})
            await self.redis.expire(_presence_key(uid), PRESENCE_STALE_MS // 1000 * 2)
        except Exception as exc:
            logger.warning("Presence add failed for user %s: %s", uid, exc)

    async def _presence_remove(self, uid: int, conn_id: str) -> None:
        try:
            await self.redis.zrem(_presence_key(uid), conn_id)
        except Exception as exc:
            logger.warning("Presence remove failed for user %s: %s", uid, exc)

    async def is_user_online(self, user_id: int) -> bool:
        """
        Whether the user has a live connection on any worker: local sockets or a fresh mark in Redis
        (stale marks are removed along the way). On a Redis failure and with no local sockets -- False.
        """
        uid = int(user_id)
        if self._has_open_sockets(uid):
            return True
        try:
            key = _presence_key(uid)
            await self.redis.zremrangebyscore(key, 0, _now_ms() - PRESENCE_STALE_MS)
            return int(await self.redis.zcard(key)) > 0
        except Exception as exc:
            logger.warning("Presence check failed for user %s: %s", uid, exc)
            return False

    # ------------------------------------------------------------------ connections

    async def connect(self, websocket: WebSocket, user_id: int):
        """
        A new player connection: accept, mark presence in Redis, subscribe to the channel of their messages and tell
        the ongoing game that the player is back.
        """
        uid = int(user_id)
        await websocket.accept()
        conn_id = uuid.uuid4().hex
        self._connections[websocket] = (uid, conn_id)
        self.active_connections[uid] = websocket
        self._user_sockets.setdefault(uid, set()).add(websocket)
        await self._presence_add(uid, conn_id)

        try:
            await self.pubsub.subscribe(f"user:{uid}")
        except Exception as exc:
            logger.warning("PubSub subscribe warning for user %s: %s", uid, exc)
        self._ensure_background_tasks()

        from src.services.game_state import state_manager
        await state_manager.handle_player_reconnect(uid, self)

        logger.info("User %s connected. Active users on worker: %s", uid, len(self.active_connections))

    async def disconnect(self, user_id: int, websocket: WebSocket | None = None):
        """
        Closes one connection of the user. While at least one tab remains open on
        any worker, they are considered online: the queue, spectating and the game are not affected.
        websocket=None closes all the user's local connections.

        Between awaits the user may reconnect (page reload, including
        to another worker), so presence is re-checked. A new connection is first
        registered in Redis and only then calls handle_player_reconnect, so with
        any order of events the disconnect flag is either not set or is cleared.
        """
        uid = int(user_id)

        closing = list(self._user_sockets.pop(uid, set())) if websocket is None else [websocket]
        for ws in closing:
            sockets = self._user_sockets.get(uid)
            if sockets is not None:
                sockets.discard(ws)
            conn = self._connections.pop(ws, None)
            if conn is not None:
                await self._presence_remove(uid, conn[1])

        if self._has_open_sockets(uid):
            self.active_connections[uid] = next(iter(self._user_sockets[uid]))
            return

        self._user_sockets.pop(uid, None)
        self.active_connections.pop(uid, None)

        try:
            await self.pubsub.unsubscribe(f"user:{uid}")
        except Exception:
            pass

        if self._has_open_sockets(uid):
            # Reconnected on this worker during the unsubscribe -- restore the subscription.
            try:
                await self.pubsub.subscribe(f"user:{uid}")
            except Exception as exc:
                logger.warning("PubSub resubscribe warning for user %s: %s", uid, exc)
            return

        if await self.is_user_online(uid):
            return  # a tab is open on another worker

        await self.remove_user_from_all_spectating(uid)

        from src.services.matchmaker import matchmaker
        await matchmaker.leave_queue(uid)

        if await self.is_user_online(uid):
            return

        from src.services.game_state import state_manager
        await state_manager.handle_player_disconnect(uid, self)

        if await self.is_user_online(uid):
            await state_manager.handle_player_reconnect(uid, self)
            return

        logger.info("User %s disconnected.", uid)

    # ------------------------------------------------------------------ delivery

    async def _deliver_local(self, user_id: int, raw_text: str) -> bool:
        """
        Instantly sends JSON to all of the user's tabs open on this worker. Returns whether at least one
        got it; sockets that could not be sent to are dropped from the registry.
        """
        uid = int(user_id)
        sockets = list(self._user_sockets.get(uid, set()))

        delivered = False
        dead_sockets: list[WebSocket] = []

        for ws in sockets:
            try:
                await ws.send_text(raw_text)
                delivered = True
            except Exception:
                dead_sockets.append(ws)

        for dead_ws in dead_sockets:
            if uid in self._user_sockets:
                self._user_sockets[uid].discard(dead_ws)
            if self.active_connections.get(uid) is dead_ws:
                self.active_connections.pop(uid, None)

        return delivered

    async def revoke_sessions(self, user_id: int) -> None:
        """
        The user's tokens are revoked (password change, "sign out everywhere", account deletion): we tell all
        of their tabs and close their WebSocket -- at once on this worker, on the others when the
        event arrives via pub/sub. Otherwise an already open connection would keep working with the old
        token. The client understands code 1008 as "session invalid, sign in again".
        """
        await self.send_personal_message({"event": SESSION_REVOKED_EVENT}, user_id)
        await self._close_local_sockets(int(user_id))

    async def _close_local_sockets(self, uid: int) -> None:
        for ws in list(self._user_sockets.get(uid, set())):
            try:
                await ws.close(code=WS_CLOSE_SESSION_REVOKED)
            except Exception:
                pass  # the socket is already closed; disconnect in the connection handler will remove it

    async def send_personal_message(self, message: dict, user_id: int):
        """
        Delivers a message to the user's tabs on this worker and publishes it for
        the other workers (a user may have tabs on several processes).
        """
        uid = int(user_id)
        payload_str = json.dumps(message)
        await self._deliver_local(uid, payload_str)

        envelope = json.dumps({"origin": self.worker_id, "data": payload_str})
        try:
            await self.redis.publish(f"user:{uid}", envelope)
        except Exception as exc:
            logger.error("Failed to publish message for user %s: %s", uid, exc)

    # ------------------------------------------------------------------ spectators

    async def add_spectator(self, game_id: int, user_id: int) -> None:
        """
        Records the player as a game spectator. One game can be watched at a time: the previous record is removed. Both records
        (the game's spectator set and the player's back reference) live SPECTATING_TTL_S.
        """
        gid, uid = int(game_id), int(user_id)
        await self.remove_user_from_all_spectating(uid)
        await self.redis.sadd(_spectators_key(gid), str(uid))
        await self.redis.expire(_spectators_key(gid), SPECTATING_TTL_S)
        await self.redis.set(_spectating_key(uid), str(gid), ex=SPECTATING_TTL_S)

    async def remove_spectator(self, game_id: int, user_id: int) -> None:
        gid, uid = int(game_id), int(user_id)
        await self.redis.srem(_spectators_key(gid), str(uid))
        if await self.redis.get(_spectating_key(uid)) == str(gid):
            await self.redis.delete(_spectating_key(uid))

    async def remove_user_from_all_spectating(self, user_id: int) -> None:
        """
        Removes the player from the spectators of the game they are watching (by the back reference user:{uid}:spectating).
        """
        uid = int(user_id)
        gid = await self.redis.get(_spectating_key(uid))
        if gid:
            await self.redis.srem(_spectators_key(int(gid)), str(uid))
            await self.redis.delete(_spectating_key(uid))

    async def get_spectator_ids(self, game_id: int) -> set[int]:
        members = await self.redis.smembers(_spectators_key(int(game_id)))
        return {int(m) for m in members}

    async def broadcast_to_spectators(self, game_id: int, message: dict) -> None:
        """Broadcasts a message to all game spectators -- to each as a personal one, to all their tabs on all workers."""
        for uid in await self.get_spectator_ids(game_id):
            await self.send_personal_message(message, uid)


manager = ConnectionManager()
