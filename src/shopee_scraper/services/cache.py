"""Redis-based caching layer for scraped data."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from shopee_scraper.utils.logging import get_logger


if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger(__name__)


class ProductCache:
    """
    Redis-based cache for product data.

    Caches scraped product details to reduce redundant scraping operations.
    Uses TTL-based expiration to ensure data freshness.
    """

    # Redis key prefix for product cache
    _KEY_PREFIX = "cache:product"

    def __init__(self, redis: Redis, ttl_seconds: int = 3600) -> None:
        """
        Initialize product cache.

        Args:
            redis: Async Redis client with connection pool
            ttl_seconds: Time-to-live for cached products (default: 1 hour)
        """
        self._redis = redis
        self._ttl = ttl_seconds

    def _make_key(self, shop_id: int, item_id: int) -> str:
        """Generate cache key for a product."""
        return f"{self._KEY_PREFIX}:{shop_id}:{item_id}"

    async def get(self, shop_id: int, item_id: int) -> dict[str, Any] | None:
        """
        Get cached product data.

        Args:
            shop_id: Shopee shop ID
            item_id: Shopee item ID

        Returns:
            Cached product data dict or None if not cached/expired
        """
        key = self._make_key(shop_id, item_id)
        try:
            data = await self._redis.get(key)
            if data:
                logger.debug(f"Cache HIT: {key}")
                return json.loads(data)
            logger.debug(f"Cache MISS: {key}")
            return None
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
            return None

    async def set(
        self,
        shop_id: int,
        item_id: int,
        data: dict[str, Any],
        ttl: int | None = None,
    ) -> bool:
        """
        Cache product data.

        Args:
            shop_id: Shopee shop ID
            item_id: Shopee item ID
            data: Product data to cache
            ttl: Optional custom TTL (uses default if not provided)

        Returns:
            True if cached successfully
        """
        key = self._make_key(shop_id, item_id)
        ttl_seconds = ttl or self._ttl

        try:
            await self._redis.setex(key, ttl_seconds, json.dumps(data))
            logger.debug(f"Cache SET: {key} (TTL: {ttl_seconds}s)")
            return True
        except Exception as e:
            logger.warning(f"Cache set error: {e}")
            return False

    async def delete(self, shop_id: int, item_id: int) -> bool:
        """
        Delete cached product data.

        Args:
            shop_id: Shopee shop ID
            item_id: Shopee item ID

        Returns:
            True if deleted successfully
        """
        key = self._make_key(shop_id, item_id)
        try:
            await self._redis.delete(key)
            logger.debug(f"Cache DELETE: {key}")
            return True
        except Exception as e:
            logger.warning(f"Cache delete error: {e}")
            return False

    async def exists(self, shop_id: int, item_id: int) -> bool:
        """Check if product is cached."""
        key = self._make_key(shop_id, item_id)
        try:
            return bool(await self._redis.exists(key))
        except Exception:
            return False

    async def get_stats(self) -> dict[str, Any]:
        """Get cache statistics (approximate count of cached products)."""
        try:
            # Use SCAN to count keys with our prefix (non-blocking)
            count = 0
            cursor = 0
            pattern = f"{self._KEY_PREFIX}:*"

            while True:
                cursor, keys = await self._redis.scan(
                    cursor=cursor, match=pattern, count=100
                )
                count += len(keys)
                if cursor == 0:
                    break

            return {
                "cached_products": count,
                "ttl_seconds": self._ttl,
                "key_prefix": self._KEY_PREFIX,
            }
        except Exception as e:
            logger.warning(f"Cache stats error: {e}")
            return {"error": str(e)}


class ReviewCache:
    """
    Redis-based cache for review data.

    Similar to ProductCache but for product reviews.
    """

    _KEY_PREFIX = "cache:reviews"

    def __init__(self, redis: Redis, ttl_seconds: int = 1800) -> None:
        """
        Initialize review cache.

        Args:
            redis: Async Redis client
            ttl_seconds: Time-to-live for cached reviews (default: 30 minutes)
        """
        self._redis = redis
        self._ttl = ttl_seconds

    def _make_key(self, shop_id: int, item_id: int) -> str:
        """Generate cache key for reviews."""
        return f"{self._KEY_PREFIX}:{shop_id}:{item_id}"

    async def get(self, shop_id: int, item_id: int) -> list[dict[str, Any]] | None:
        """Get cached reviews."""
        key = self._make_key(shop_id, item_id)
        try:
            data = await self._redis.get(key)
            if data:
                logger.debug(f"Review cache HIT: {key}")
                return json.loads(data)
            return None
        except Exception as e:
            logger.warning(f"Review cache get error: {e}")
            return None

    async def set(
        self,
        shop_id: int,
        item_id: int,
        reviews: list[dict[str, Any]],
        ttl: int | None = None,
    ) -> bool:
        """Cache reviews."""
        key = self._make_key(shop_id, item_id)
        try:
            await self._redis.setex(key, ttl or self._ttl, json.dumps(reviews))
            return True
        except Exception as e:
            logger.warning(f"Review cache set error: {e}")
            return False
