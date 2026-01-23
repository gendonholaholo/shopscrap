"""Rate limiter middleware using SlowAPI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from shopee_scraper.utils.config import get_settings
from shopee_scraper.utils.logging import get_logger


if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI, Request

logger = get_logger(__name__)


def get_client_ip(request: Request) -> str:
    """
    Get client IP address from request.

    Handles proxied requests by checking X-Forwarded-For header.
    """
    # Check for forwarded IP (behind proxy/load balancer)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For can contain multiple IPs, first one is the client
        return forwarded_for.split(",")[0].strip()

    # Check X-Real-IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # Fall back to direct connection IP
    return get_remote_address(request)


def create_limiter() -> Limiter:
    """
    Create and configure rate limiter based on settings.

    Returns:
        Configured Limiter instance
    """
    settings = get_settings()
    rate_limit_config = settings.rate_limit

    # Determine storage backend
    if rate_limit_config.storage == "redis" and rate_limit_config.redis_url:
        try:
            from slowapi.middleware import SlowAPIASGIMiddleware  # noqa: F401

            storage_uri = rate_limit_config.redis_url
            logger.info("Rate limiter using Redis storage", redis_url=storage_uri)
        except ImportError:
            logger.warning("Redis not available, falling back to memory storage")
            storage_uri = None
    else:
        storage_uri = None
        logger.info("Rate limiter using in-memory storage")

    # Create limiter with key function
    limiter = Limiter(
        key_func=get_client_ip,
        storage_uri=storage_uri,
        default_limits=[
            f"{rate_limit_config.requests_per_minute}/minute",
            f"{rate_limit_config.requests_per_hour}/hour",
        ],
    )

    return limiter


# Global limiter instance
_limiter: Limiter | None = None


def get_limiter() -> Limiter:
    """Get or create global limiter instance."""
    global _limiter  # noqa: PLW0603
    if _limiter is None:
        _limiter = create_limiter()
    return _limiter


def setup_rate_limiter(app: FastAPI) -> Limiter | None:
    """
    Setup rate limiter for FastAPI application.

    Args:
        app: FastAPI application instance

    Returns:
        Limiter instance if enabled, None otherwise
    """
    settings = get_settings()

    if not settings.rate_limit.enabled:
        logger.info("Rate limiting is DISABLED")
        return None

    limiter = get_limiter()

    # Attach limiter to app state
    app.state.limiter = limiter

    # Add exception handler for rate limit exceeded
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    logger.info(
        "Rate limiting ENABLED",
        requests_per_minute=settings.rate_limit.requests_per_minute,
        requests_per_hour=settings.rate_limit.requests_per_hour,
        storage=settings.rate_limit.storage,
    )

    return limiter


def rate_limit(limit: str | None = None) -> Callable:
    """
    Decorator for rate limiting specific endpoints.

    Usage:
        @router.get("/search")
        @rate_limit("10/minute")
        async def search(...):
            ...

    Args:
        limit: Rate limit string (e.g., "10/minute", "100/hour")
               If None, uses default limits from settings

    Returns:
        Decorator function
    """
    settings = get_settings()

    # If rate limiting is disabled, return a no-op decorator
    if not settings.rate_limit.enabled:

        def no_op_decorator(func: Callable) -> Callable:
            return func

        return no_op_decorator

    limiter = get_limiter()

    if limit:
        return limiter.limit(limit)
    else:
        # Use default limit
        return limiter.limit(f"{settings.rate_limit.requests_per_minute}/minute")


# Predefined rate limit decorators for common use cases
def rate_limit_search() -> Callable:
    """Rate limit for search endpoints (more restrictive)."""
    return rate_limit("30/minute")


def rate_limit_product() -> Callable:
    """Rate limit for product detail endpoints."""
    return rate_limit("60/minute")


def rate_limit_reviews() -> Callable:
    """Rate limit for review endpoints."""
    return rate_limit("30/minute")


def rate_limit_health() -> Callable:
    """Rate limit for health check endpoints (lenient)."""
    return rate_limit("120/minute")
