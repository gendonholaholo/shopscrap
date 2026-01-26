"""FastAPI dependencies for dependency injection."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from redis.asyncio import ConnectionPool, Redis

from shopee_scraper.api.auth import get_api_key, optional_api_key
from shopee_scraper.services.scraper_service import ScraperService
from shopee_scraper.utils.config import get_settings
from shopee_scraper.utils.logging import get_logger


logger = get_logger(__name__)

# Global service instances (singleton pattern)
_scraper_service: ScraperService | None = None
_redis_pool: ConnectionPool | None = None
_redis_client: Redis | None = None


async def get_scraper_service() -> ScraperService:
    """Get or create scraper service instance."""
    global _scraper_service  # noqa: PLW0603
    if _scraper_service is None:
        _scraper_service = ScraperService(headless=True)
    return _scraper_service


async def cleanup_scraper_service() -> None:
    """Cleanup scraper service on shutdown."""
    global _scraper_service  # noqa: PLW0603
    if _scraper_service:
        await _scraper_service.close()
        _scraper_service = None


async def get_redis() -> Redis:
    """
    Get async Redis client with connection pooling.

    Uses a shared connection pool for better performance under load.
    Pool configuration is controlled via JOB_QUEUE_REDIS_POOL_SIZE and
    JOB_QUEUE_REDIS_POOL_TIMEOUT environment variables.
    """
    global _redis_pool, _redis_client  # noqa: PLW0603

    if _redis_client is None:
        settings = get_settings()
        job_queue_settings = settings.job_queue

        # Create connection pool
        _redis_pool = ConnectionPool.from_url(
            job_queue_settings.redis_url,
            max_connections=job_queue_settings.redis_pool_size,
            socket_timeout=job_queue_settings.redis_pool_timeout,
            decode_responses=True,
        )

        # Create Redis client using the pool
        _redis_client = Redis(connection_pool=_redis_pool)

        logger.info(
            "Redis connection pool initialized",
            pool_size=job_queue_settings.redis_pool_size,
            url=job_queue_settings.redis_url.split("@")[-1],  # Hide credentials
        )

    return _redis_client


async def cleanup_redis() -> None:
    """Close Redis connection pool on shutdown."""
    global _redis_pool, _redis_client  # noqa: PLW0603

    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None

    if _redis_pool:
        await _redis_pool.disconnect()
        _redis_pool = None
        logger.info("Redis connection pool closed")


# Type aliases for dependency injection
ScraperServiceDep = Annotated[ScraperService, Depends(get_scraper_service)]

# API Key dependencies
RequireApiKey = Annotated[str, Depends(get_api_key)]
OptionalApiKey = Annotated[str | None, Depends(optional_api_key)]
