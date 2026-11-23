"""
On failure the Redis client answers quickly: fail-open settings (rate_limit etc.) assume short
timeouts, while the default redis-py retries (10 s with growing backoff) stretched every call to ~15 s.
"""

import socket
import time

import pytest
import redis.asyncio as redis

from src.core.config import settings
from src.db import redis as redis_module


def test_client_retries_are_bounded_and_immediate():
    retry = redis_module.create_redis_client().get_retry()
    assert retry._retries == settings.REDIS_RETRIES <= 1
    assert retry._backoff.compute(1) == 0


async def test_unreachable_redis_fails_within_a_few_timeouts():
    with socket.socket() as probe:  # guaranteed free port
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    client = redis_module.create_redis_client(
        host="127.0.0.1", port=port, socket_connect_timeout=0.3, socket_timeout=0.3,
    )
    started = time.perf_counter()
    with pytest.raises((redis.ConnectionError, redis.TimeoutError)):
        await client.ping()
    assert time.perf_counter() - started < 0.3 * (1 + settings.REDIS_RETRIES) + 1.0
    await client.aclose()
