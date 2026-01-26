"""Unit tests for ProductCache and ReviewCache."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from shopee_scraper.services.cache import ProductCache, ReviewCache


class TestProductCacheInit:
    """Tests for ProductCache initialization."""

    def test_init_with_redis_client(self) -> None:
        """Cache initializes with Redis client."""
        mock_redis = MagicMock()
        cache = ProductCache(redis=mock_redis)

        assert cache._redis == mock_redis

    def test_init_default_ttl(self) -> None:
        """Default TTL is 3600 seconds (1 hour)."""
        mock_redis = MagicMock()
        cache = ProductCache(redis=mock_redis)

        assert cache._ttl == 3600

    def test_init_custom_ttl(self) -> None:
        """Custom TTL can be set."""
        mock_redis = MagicMock()
        cache = ProductCache(redis=mock_redis, ttl_seconds=7200)

        assert cache._ttl == 7200


class TestProductCacheKeyFormat:
    """Tests for cache key generation."""

    def test_make_key_format(self) -> None:
        """Key follows format: cache:product:shop_id:item_id."""
        mock_redis = MagicMock()
        cache = ProductCache(redis=mock_redis)

        key = cache._make_key(shop_id=12345, item_id=67890)

        assert key == "cache:product:12345:67890"

    def test_make_key_different_ids(self) -> None:
        """Different IDs produce different keys."""
        mock_redis = MagicMock()
        cache = ProductCache(redis=mock_redis)

        key1 = cache._make_key(shop_id=111, item_id=222)
        key2 = cache._make_key(shop_id=333, item_id=444)

        assert key1 != key2
        assert key1 == "cache:product:111:222"
        assert key2 == "cache:product:333:444"


class TestProductCacheGet:
    """Tests for cache get operations."""

    @pytest.mark.asyncio
    async def test_get_cache_miss_returns_none(self) -> None:
        """Cache miss returns None."""
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=None)
        cache = ProductCache(redis=mock_redis)

        result = await cache.get(shop_id=123, item_id=456)

        assert result is None
        mock_redis.get.assert_called_once_with("cache:product:123:456")

    @pytest.mark.asyncio
    async def test_get_cache_hit_returns_data(self) -> None:
        """Cache hit returns parsed JSON data."""
        mock_redis = MagicMock()
        product_data = {"name": "Test Product", "price": 100000}
        mock_redis.get = AsyncMock(return_value=json.dumps(product_data))
        cache = ProductCache(redis=mock_redis)

        result = await cache.get(shop_id=123, item_id=456)

        assert result == product_data

    @pytest.mark.asyncio
    async def test_get_redis_error_returns_none(self) -> None:
        """Redis error returns None gracefully."""
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(side_effect=Exception("Redis connection error"))
        cache = ProductCache(redis=mock_redis)

        result = await cache.get(shop_id=123, item_id=456)

        assert result is None


class TestProductCacheSet:
    """Tests for cache set operations."""

    @pytest.mark.asyncio
    async def test_set_stores_data_with_ttl(self) -> None:
        """Set stores JSON data with TTL."""
        mock_redis = MagicMock()
        mock_redis.setex = AsyncMock()
        cache = ProductCache(redis=mock_redis, ttl_seconds=3600)
        product_data = {"name": "Test Product", "price": 100000}

        result = await cache.set(shop_id=123, item_id=456, data=product_data)

        assert result is True
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == "cache:product:123:456"
        assert call_args[0][1] == 3600
        assert json.loads(call_args[0][2]) == product_data

    @pytest.mark.asyncio
    async def test_set_custom_ttl(self) -> None:
        """Set with custom TTL overrides default."""
        mock_redis = MagicMock()
        mock_redis.setex = AsyncMock()
        cache = ProductCache(redis=mock_redis, ttl_seconds=3600)

        await cache.set(shop_id=123, item_id=456, data={"test": 1}, ttl=600)

        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 600  # Custom TTL

    @pytest.mark.asyncio
    async def test_set_redis_error_returns_false(self) -> None:
        """Redis error returns False."""
        mock_redis = MagicMock()
        mock_redis.setex = AsyncMock(side_effect=Exception("Redis error"))
        cache = ProductCache(redis=mock_redis)

        result = await cache.set(shop_id=123, item_id=456, data={"test": 1})

        assert result is False


class TestProductCacheDelete:
    """Tests for cache delete operations."""

    @pytest.mark.asyncio
    async def test_delete_removes_key(self) -> None:
        """Delete removes key from Redis."""
        mock_redis = MagicMock()
        mock_redis.delete = AsyncMock()
        cache = ProductCache(redis=mock_redis)

        result = await cache.delete(shop_id=123, item_id=456)

        assert result is True
        mock_redis.delete.assert_called_once_with("cache:product:123:456")

    @pytest.mark.asyncio
    async def test_delete_redis_error_returns_false(self) -> None:
        """Redis error returns False."""
        mock_redis = MagicMock()
        mock_redis.delete = AsyncMock(side_effect=Exception("Redis error"))
        cache = ProductCache(redis=mock_redis)

        result = await cache.delete(shop_id=123, item_id=456)

        assert result is False


class TestProductCacheExists:
    """Tests for cache exists check."""

    @pytest.mark.asyncio
    async def test_exists_returns_true_when_cached(self) -> None:
        """Returns True when key exists."""
        mock_redis = MagicMock()
        mock_redis.exists = AsyncMock(return_value=1)
        cache = ProductCache(redis=mock_redis)

        result = await cache.exists(shop_id=123, item_id=456)

        assert result is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_when_not_cached(self) -> None:
        """Returns False when key doesn't exist."""
        mock_redis = MagicMock()
        mock_redis.exists = AsyncMock(return_value=0)
        cache = ProductCache(redis=mock_redis)

        result = await cache.exists(shop_id=123, item_id=456)

        assert result is False

    @pytest.mark.asyncio
    async def test_exists_error_returns_false(self) -> None:
        """Redis error returns False."""
        mock_redis = MagicMock()
        mock_redis.exists = AsyncMock(side_effect=Exception("Redis error"))
        cache = ProductCache(redis=mock_redis)

        result = await cache.exists(shop_id=123, item_id=456)

        assert result is False


class TestReviewCacheInit:
    """Tests for ReviewCache initialization."""

    def test_init_default_ttl(self) -> None:
        """Default TTL is 1800 seconds (30 minutes)."""
        mock_redis = MagicMock()
        cache = ReviewCache(redis=mock_redis)

        assert cache._ttl == 1800

    def test_key_prefix_different_from_product(self) -> None:
        """Review cache uses different key prefix."""
        mock_redis = MagicMock()
        cache = ReviewCache(redis=mock_redis)

        key = cache._make_key(shop_id=123, item_id=456)

        assert key == "cache:reviews:123:456"
        assert "product" not in key


class TestReviewCacheGet:
    """Tests for ReviewCache get operations."""

    @pytest.mark.asyncio
    async def test_get_returns_list_of_reviews(self) -> None:
        """Cache hit returns list of review dicts."""
        mock_redis = MagicMock()
        reviews = [
            {"rating": 5, "comment": "Great!"},
            {"rating": 4, "comment": "Good"},
        ]
        mock_redis.get = AsyncMock(return_value=json.dumps(reviews))
        cache = ReviewCache(redis=mock_redis)

        result = await cache.get(shop_id=123, item_id=456)

        assert result == reviews
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_cache_miss_returns_none(self) -> None:
        """Cache miss returns None."""
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=None)
        cache = ReviewCache(redis=mock_redis)

        result = await cache.get(shop_id=123, item_id=456)

        assert result is None


class TestReviewCacheSet:
    """Tests for ReviewCache set operations."""

    @pytest.mark.asyncio
    async def test_set_stores_review_list(self) -> None:
        """Set stores list of reviews."""
        mock_redis = MagicMock()
        mock_redis.setex = AsyncMock()
        cache = ReviewCache(redis=mock_redis)
        reviews = [{"rating": 5, "comment": "Excellent!"}]

        result = await cache.set(shop_id=123, item_id=456, reviews=reviews)

        assert result is True
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_redis_error_returns_false(self) -> None:
        """Redis error returns False."""
        mock_redis = MagicMock()
        mock_redis.setex = AsyncMock(side_effect=Exception("Redis error"))
        cache = ReviewCache(redis=mock_redis)

        result = await cache.set(shop_id=123, item_id=456, reviews=[])

        assert result is False


class TestCacheIntegration:
    """Integration-style tests for cache behavior."""

    @pytest.mark.asyncio
    async def test_product_cache_roundtrip(self) -> None:
        """Data can be set and retrieved."""
        # Use a simple in-memory store to simulate Redis
        store: dict[str, str] = {}

        mock_redis = MagicMock()
        mock_redis.setex = AsyncMock(
            side_effect=lambda k, t, v: store.update({k: v}) or None
        )
        mock_redis.get = AsyncMock(side_effect=lambda k: store.get(k))

        cache = ProductCache(redis=mock_redis)
        product = {"name": "Test", "price": 50000}

        # Set
        await cache.set(shop_id=1, item_id=2, data=product)

        # Get
        result = await cache.get(shop_id=1, item_id=2)

        assert result == product

    @pytest.mark.asyncio
    async def test_different_products_different_cache_entries(self) -> None:
        """Different products have separate cache entries."""
        store: dict[str, str] = {}

        mock_redis = MagicMock()
        mock_redis.setex = AsyncMock(
            side_effect=lambda k, t, v: store.update({k: v}) or None
        )
        mock_redis.get = AsyncMock(side_effect=lambda k: store.get(k))

        cache = ProductCache(redis=mock_redis)

        # Set two different products
        await cache.set(shop_id=1, item_id=100, data={"name": "Product A"})
        await cache.set(shop_id=1, item_id=200, data={"name": "Product B"})

        # Retrieve both
        result_a = await cache.get(shop_id=1, item_id=100)
        result_b = await cache.get(shop_id=1, item_id=200)

        assert result_a["name"] == "Product A"
        assert result_b["name"] == "Product B"
