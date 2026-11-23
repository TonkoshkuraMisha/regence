# --- FILE: tests/integration/conftest.py ---
"""
Shared fixtures for integration tests on a real PostgreSQL: an empty schema built from the models for each test and a
session factory without a connection pool (each competing session has its own connection, otherwise the races are fake).
The database address is the TEST_DATABASE_URL variable (set in CI by .github/workflows/ci.yml); without it the
module tests are skipped by their own skipif marker.
"""

import os

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.models.base import Base

DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.fixture
async def pg():
    """Session factory for the real database; the schema is recreated before a test and dropped after."""
    engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
