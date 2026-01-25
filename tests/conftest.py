"""Pytest configuration and fixtures."""

from __future__ import annotations

import pytest
from fakeredis.aioredis import FakeRedis

from shopee_scraper.api.jobs import RedisJobQueue
from shopee_scraper.utils.config import JobQueueSettings


@pytest.fixture
def sample_product_data() -> dict:
    """Sample product data for testing."""
    return {
        "item_id": 12345678,
        "shop_id": 87654321,
        "name": "Test Product",
        "price": 150000.0,
        "stock": 100,
        "sold": 50,
        "rating": 4.5,
        "url": "https://shopee.co.id/product/87654321/12345678",
    }


@pytest.fixture
def sample_search_results() -> list[dict]:
    """Sample search results for testing."""
    return [
        {"item_id": 1, "name": "Product 1", "price": 10000},
        {"item_id": 2, "name": "Product 2", "price": 20000},
        {"item_id": 3, "name": "Product 3", "price": 30000},
    ]


@pytest.fixture
async def redis_client() -> FakeRedis:
    """Create a fresh fakeredis instance for testing."""
    client = FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
def job_queue_settings() -> JobQueueSettings:
    """Job queue settings optimized for testing."""
    return JobQueueSettings(
        redis_url="redis://localhost:6379/15",  # unused, fakeredis
        max_concurrent=2,
        job_ttl_hours=1,
        max_retries=3,
        retry_delay_seconds=0,  # No delay in tests
        handler_timeout_seconds=5,  # Short timeout for tests
        max_queue_size=10,
        cleanup_interval_seconds=3600,
    )


@pytest.fixture
async def job_queue(
    redis_client: FakeRedis,
    job_queue_settings: JobQueueSettings,
) -> RedisJobQueue:
    """Create a RedisJobQueue instance with fakeredis."""
    queue = RedisJobQueue(redis=redis_client, settings=job_queue_settings)
    yield queue
    # Ensure stopped after test
    if queue._running:
        await queue.stop()
