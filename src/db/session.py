"""
The PostgreSQL connection: the asynchronous SQLAlchemy engine and the session factory.

The database address is assembled from the POSTGRES_* settings (settings.async_database_url), the pool size - DB_POOL_SIZE and
DB_MAX_OVERFLOW per API process. Two ways to get a session:

* get_db - a FastAPI dependency for an HTTP request: the session lives until the end of the request;
* get_session_factory - a factory for long-lived connections (WebSocket): the handler opens a short session per
  action, otherwise a pool connection would be busy all the time the player's tab is open.

Celery background tasks create their own engine for each task (src/worker/tasks.py).
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import settings
from src.core.observability import instrument_engine

# The engine - one per API process. pool_timeout - how long a request waits for a free connection (DB_POOL_TIMEOUT_S);
# pool_pre_ping checks the connection before handing it out so that after a PostgreSQL restart requests do not fail on
# broken connections. instrument_engine counts busy connections for the regence_db_pool_checked_out metric.
engine = create_async_engine(
    settings.async_database_url,
    echo=False,
    future=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT_S,
    pool_pre_ping=True,
)
instrument_engine(engine)

# The session factory. expire_on_commit=False: objects stay readable after commit - WebSocket handlers
# release the connection before sending the reply and keep using the already loaded data.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


async def get_db():
    """
    A FastAPI dependency: a database session for one HTTP request, closed after the response. It commits nothing itself -
    changes are saved by the handler or the service.

    For HTTP requests only: the session lives until the end of the request. Long-lived handlers
    (WebSocket) need the get_session_factory factory and a short session for each operation.
    """
    async with AsyncSessionLocal() as session:
        yield session


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    A FastAPI dependency: a session factory for long-lived connections.

    A session from get_db taken by a WebSocket handler would live for the whole connection: the very first query
    opens a transaction, and the pool connection stays busy ("idle in transaction") while
    the player is connected. So a WebSocket opens a short session for each action.
    """
    return AsyncSessionLocal
