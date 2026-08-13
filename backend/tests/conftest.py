import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings


@pytest_asyncio.fixture
async def db_session():
    """A DB session whose transaction is always rolled back — no test data persists.

    Runs against the real dev Postgres (needed for the pgvector column type), not sqlite.
    Uses its own engine (rather than the app's module-level singleton) and disposes it at
    teardown, since pytest-asyncio gives each test function a fresh event loop and asyncpg
    connections can't be reused across event loops.
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()
