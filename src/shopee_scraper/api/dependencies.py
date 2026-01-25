"""FastAPI dependencies for dependency injection."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis

from shopee_scraper.api.auth import get_api_key, optional_api_key
from shopee_scraper.services.scraper_service import ScraperService
from shopee_scraper.utils.config import get_settings


# Global service instances (singleton pattern)
_scraper_service: ScraperService | None = None
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
    """Get or create async Redis client for job queue."""
    global _redis_client  # noqa: PLW0603
    if _redis_client is None:
        settings = get_settings()
        _redis_client = Redis.from_url(
            settings.job_queue.redis_url,
            decode_responses=True,
        )
    return _redis_client


async def cleanup_redis() -> None:
    """Close Redis connection on shutdown."""
    global _redis_client  # noqa: PLW0603
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None


# Type aliases for dependency injection
ScraperServiceDep = Annotated[ScraperService, Depends(get_scraper_service)]

# API Key dependencies
RequireApiKey = Annotated[str, Depends(get_api_key)]
OptionalApiKey = Annotated[str | None, Depends(optional_api_key)]
