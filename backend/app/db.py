from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.normalize_database_url(),
            # replicas x uvicorn workers x pool_size must fit Postgres max_connections.
            # Keep this small; turn on Railway's PgBouncer before scaling past one replica.
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
            echo=False,
            # Otherwise Postgres returns timestamptz values in the connection's local
            # timezone, not UTC — two reads of the same instant compare unequal once
            # serialized (caught by a profile test comparing onboarding_completed_at
            # across two API calls).
            connect_args={"options": "-c timezone=utc"},
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. Commits on clean exit, rolls back on exception."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
