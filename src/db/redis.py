"""
The Redis client - shared by the API and services (redis_client).

The address is the REDIS_HOST and REDIS_PORT settings. Timeouts are short, retries are few (REDIS_CONNECT_TIMEOUT_S,
REDIS_SOCKET_TIMEOUT_S, REDIS_RETRIES): when Redis is unavailable a call must quickly return an error and not hold
login, moves and WebSocket for fifteen seconds. What exactly is stored in Redis - docs/ARCHITECTURE.md, section 3.
"""

from typing import Any

import redis.asyncio as redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff

from src.core.config import settings


def create_redis_client(**overrides: Any) -> redis.Redis:
    """
    A Redis client with short timeouts and limited retries.

    redis-py 8 by default retries a command 10 times with a growing pause: when Redis is unavailable
    every call hung for ~15 s, and login, moves and WebSocket froze instead of a quick fail-open.
    One immediate retry survives a connection broken after a Redis restart.
    """
    options: dict[str, Any] = {
        "host": settings.REDIS_HOST,
        "port": settings.REDIS_PORT,
        "decode_responses": True,
        "socket_connect_timeout": settings.REDIS_CONNECT_TIMEOUT_S,
        "socket_timeout": settings.REDIS_SOCKET_TIMEOUT_S,
        "retry": Retry(NoBackoff(), settings.REDIS_RETRIES),
    }
    options.update(overrides)
    return redis.Redis(**options)


# The global asynchronous Redis client.
# The type Any is deliberate: with decode_responses=True all replies are str, but the redis-py type stubs
# do not express this and describe every reply as bytes | str. Without Any mypy would require
# decoding what is already decoded at every place of use.
redis_client: Any = create_redis_client()
