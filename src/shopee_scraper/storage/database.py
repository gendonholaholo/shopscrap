"""Async PostgreSQL database engine and session management."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shopee_scraper.utils.logging import get_logger


if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine

logger = get_logger(__name__)

# Module-level singleton
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db(database_url: str) -> None:
    """Initialize the async engine and create all tables.

    Args:
        database_url: PostgreSQL connection URL
            (e.g. postgresql+asyncpg://user:pass@host:port/db)
    """
    global _engine, _session_factory  # noqa: PLW0603

    _engine = create_async_engine(
        database_url,
        pool_size=5,
        max_overflow=10,
        echo=False,
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    # Create tables
    from shopee_scraper.storage.models import Base

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database initialized", url=database_url.split("@")[-1])


async def close_db() -> None:
    """Dispose of the engine connection pool."""
    global _engine, _session_factory  # noqa: PLW0603
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database connection closed")


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an async database session."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")

    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
