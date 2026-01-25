"""Unit tests for Redis-backed job queue."""

from __future__ import annotations

import asyncio

import pytest

from shopee_scraper.api.jobs import (
    Job,
    JobStatus,
    QueueFullError,
    RedisJobQueue,
)


class TestJob:
    """Tests for Job dataclass."""

    def test_job_creation(self):
        job = Job(
            id="test-123",
            type="search",
            params={"keyword": "laptop"},
        )

        assert job.id == "test-123"
        assert job.type == "search"
        assert job.status == JobStatus.PENDING
        assert job.progress == 0
        assert job.result is None
        assert job.error is None
        assert job.retries == 0

    def test_job_to_dict(self):
        job = Job(
            id="test-456",
            type="batch_scrape",
            params={"keyword": "phone", "max_products": 10},
        )

        data = job.to_dict()
        assert data["id"] == "test-456"
        assert data["type"] == "batch_scrape"
        assert data["status"] == "pending"
        assert data["params"] == {"keyword": "phone", "max_products": 10}
        assert "created_at" in data
        assert data["retries"] == 0

    def test_job_json_roundtrip(self):
        job = Job(
            id="test-789",
            type="search",
            params={"keyword": "test"},
        )

        json_str = job.to_json()
        restored = Job.from_json(json_str)

        assert restored.id == job.id
        assert restored.type == job.type
        assert restored.params == job.params
        assert restored.status == job.status


class TestRedisJobQueue:
    """Tests for RedisJobQueue with fakeredis."""

    async def test_register_handler(self, job_queue: RedisJobQueue):
        async def dummy_handler(keyword: str) -> dict:
            return {"keyword": keyword}

        job_queue.register_handler("test_job", dummy_handler)
        assert "test_job" in job_queue._handlers

    async def test_submit_job(self, job_queue: RedisJobQueue):
        async def dummy_handler(keyword: str) -> dict:
            return {"keyword": keyword}

        job_queue.register_handler("search", dummy_handler)

        job = await job_queue.submit("search", {"keyword": "test"})

        assert job.id is not None
        assert job.type == "search"
        assert job.status == JobStatus.PENDING
        assert job.params == {"keyword": "test"}

    async def test_submit_unknown_job_type(self, job_queue: RedisJobQueue):
        with pytest.raises(ValueError, match="Unknown job type"):
            await job_queue.submit("unknown_type", {})

    async def test_submit_persists_to_redis(self, job_queue: RedisJobQueue):
        async def dummy_handler() -> dict:
            return {}

        job_queue.register_handler("test", dummy_handler)
        job = await job_queue.submit("test", {})

        # Verify persisted
        retrieved = await job_queue.get_job(job.id)
        assert retrieved is not None
        assert retrieved.id == job.id
        assert retrieved.type == "test"

    async def test_get_nonexistent_job(self, job_queue: RedisJobQueue):
        assert await job_queue.get_job("nonexistent") is None

    async def test_list_jobs(self, job_queue: RedisJobQueue):
        async def dummy_handler() -> dict:
            return {}

        job_queue.register_handler("test", dummy_handler)

        await job_queue.submit("test", {})
        await job_queue.submit("test", {})
        await job_queue.submit("test", {})

        jobs = await job_queue.list_jobs()
        assert len(jobs) == 3

    async def test_list_jobs_with_filter(self, job_queue: RedisJobQueue):
        async def dummy_handler() -> dict:
            return {}

        job_queue.register_handler("test", dummy_handler)

        await job_queue.submit("test", {})
        await job_queue.submit("test", {})

        pending_jobs = await job_queue.list_jobs(status=JobStatus.PENDING)
        completed_jobs = await job_queue.list_jobs(status=JobStatus.COMPLETED)

        assert len(pending_jobs) == 2
        assert len(completed_jobs) == 0

    async def test_cancel_pending_job(self, job_queue: RedisJobQueue):
        async def dummy_handler() -> dict:
            return {}

        job_queue.register_handler("test", dummy_handler)

        job = await job_queue.submit("test", {})
        result = await job_queue.cancel_job(job.id)

        assert result is True

        updated = await job_queue.get_job(job.id)
        assert updated is not None
        assert updated.status == JobStatus.CANCELLED
        assert updated.completed_at is not None

    async def test_cancel_nonexistent_job(self, job_queue: RedisJobQueue):
        result = await job_queue.cancel_job("nonexistent")
        assert result is False

    async def test_queue_full_error(self, job_queue: RedisJobQueue):
        """Test that queue rejects submissions when full."""

        async def dummy_handler() -> dict:
            return {}

        job_queue.register_handler("test", dummy_handler)

        # Fill the queue (max_queue_size=10)
        for _ in range(10):
            await job_queue.submit("test", {})

        # Next submission should fail
        with pytest.raises(QueueFullError):
            await job_queue.submit("test", {})

    async def test_job_processing(self, job_queue: RedisJobQueue):
        """Test that jobs are processed by workers."""
        result_holder: dict = {"processed": False}

        async def test_handler(value: str) -> dict:
            result_holder["processed"] = True
            return {"value": value}

        job_queue.register_handler("test", test_handler)
        await job_queue.start()

        try:
            job = await job_queue.submit("test", {"value": "hello"})

            # Wait for processing
            for _ in range(50):
                updated = await job_queue.get_job(job.id)
                if updated and updated.status == JobStatus.COMPLETED:
                    break
                await asyncio.sleep(0.1)

            assert result_holder["processed"] is True
            final = await job_queue.get_job(job.id)
            assert final is not None
            assert final.status == JobStatus.COMPLETED
            assert final.result == {"value": "hello"}
            assert final.progress == 100
        finally:
            await job_queue.stop()

    async def test_job_failure_with_retry(self, job_queue: RedisJobQueue):
        """Test that failed jobs are retried."""
        attempt_count: dict = {"count": 0}

        async def failing_handler() -> dict:
            attempt_count["count"] += 1
            raise ValueError("Test error")

        job_queue.register_handler("failing", failing_handler)
        await job_queue.start()

        try:
            job = await job_queue.submit("failing", {})

            # Wait for all retries to complete
            for _ in range(100):
                updated = await job_queue.get_job(job.id)
                if updated and updated.status == JobStatus.FAILED:
                    break
                await asyncio.sleep(0.1)

            final = await job_queue.get_job(job.id)
            assert final is not None
            assert final.status == JobStatus.FAILED
            assert final.retries == 3  # max_retries
            assert "Failed after 3 attempts" in (final.error or "")
            assert attempt_count["count"] == 3
        finally:
            await job_queue.stop()

    async def test_handler_timeout(self, job_queue: RedisJobQueue):
        """Test that handler timeout is enforced."""
        # Use a very short timeout
        job_queue._settings.handler_timeout_seconds = 1

        async def slow_handler() -> dict:
            await asyncio.sleep(10)
            return {}

        job_queue.register_handler("slow", slow_handler)
        await job_queue.start()

        try:
            job = await job_queue.submit("slow", {})

            # Wait for timeout + retries
            for _ in range(150):
                updated = await job_queue.get_job(job.id)
                if updated and updated.status == JobStatus.FAILED:
                    break
                await asyncio.sleep(0.1)

            final = await job_queue.get_job(job.id)
            assert final is not None
            assert final.status == JobStatus.FAILED
            assert "timeout" in (final.error or "").lower()
        finally:
            await job_queue.stop()

    async def test_cancel_running_job(self, job_queue: RedisJobQueue):
        """Test cancelling a running job."""
        started = asyncio.Event()

        async def long_handler() -> dict:
            started.set()
            await asyncio.sleep(60)
            return {}

        job_queue.register_handler("long", long_handler)
        await job_queue.start()

        try:
            job = await job_queue.submit("long", {})

            # Wait until the job starts running
            await asyncio.wait_for(started.wait(), timeout=5)
            await asyncio.sleep(0.1)  # Let status transition complete

            result = await job_queue.cancel_job(job.id)
            assert result is True

            final = await job_queue.get_job(job.id)
            assert final is not None
            assert final.status == JobStatus.CANCELLED
        finally:
            await job_queue.stop()

    async def test_progress_update(self, job_queue: RedisJobQueue):
        """Test progress updates."""
        progress_event = asyncio.Event()

        async def handler_with_progress() -> dict:
            # Simulate progress - the queue itself must be referenced
            progress_event.set()
            await asyncio.sleep(2)
            return {}

        job_queue.register_handler("progress_test", handler_with_progress)
        await job_queue.start()

        try:
            job = await job_queue.submit("progress_test", {})

            # Wait for job to start
            await asyncio.wait_for(progress_event.wait(), timeout=5)
            await asyncio.sleep(0.1)

            # Update progress externally
            await job_queue.update_progress(job.id, 50)

            updated = await job_queue.get_job(job.id)
            assert updated is not None
            assert updated.progress == 50
        finally:
            await job_queue.stop()

    async def test_graceful_shutdown_requeues_jobs(self, job_queue: RedisJobQueue):
        """Test that running jobs are requeued on shutdown."""
        started = asyncio.Event()

        async def long_handler() -> dict:
            started.set()
            await asyncio.sleep(60)
            return {}

        job_queue.register_handler("long", long_handler)
        await job_queue.start()

        job = await job_queue.submit("long", {})

        # Wait for job to start
        await asyncio.wait_for(started.wait(), timeout=5)
        await asyncio.sleep(0.1)

        # Stop the queue (graceful shutdown)
        await job_queue.stop()

        # Job should be requeued as PENDING
        final = await job_queue.get_job(job.id)
        assert final is not None
        assert final.status == JobStatus.PENDING

    async def test_recover_interrupted_jobs(
        self, job_queue: RedisJobQueue, redis_client
    ):
        """Test that RUNNING jobs are requeued on startup."""

        async def dummy_handler() -> dict:
            return {}

        job_queue.register_handler("test", dummy_handler)

        # Manually create a job in RUNNING state (simulating crash)
        job = await job_queue.submit("test", {})
        # Transition to RUNNING manually
        await job_queue._transition_status(job, JobStatus.RUNNING)
        await job_queue._save_job(job)

        # Start the queue - should recover
        await job_queue.start()

        try:
            # Wait for recovery + processing
            for _ in range(50):
                updated = await job_queue.get_job(job.id)
                if updated and updated.status == JobStatus.COMPLETED:
                    break
                await asyncio.sleep(0.1)

            final = await job_queue.get_job(job.id)
            assert final is not None
            assert final.status == JobStatus.COMPLETED
        finally:
            await job_queue.stop()

    async def test_concurrent_worker_limit(self, job_queue: RedisJobQueue):
        """Test that max_concurrent workers limit is enforced."""
        running_count: dict = {"current": 0, "max_seen": 0}
        lock = asyncio.Lock()

        async def concurrent_handler() -> dict:
            async with lock:
                running_count["current"] += 1
                running_count["max_seen"] = max(
                    running_count["max_seen"], running_count["current"]
                )
            await asyncio.sleep(0.5)
            async with lock:
                running_count["current"] -= 1
            return {}

        job_queue.register_handler("concurrent", concurrent_handler)
        await job_queue.start()

        try:
            # Submit more jobs than workers (max_concurrent=2)
            for _ in range(5):
                await job_queue.submit("concurrent", {})

            # Wait for all to complete
            for _ in range(100):
                jobs = await job_queue.list_jobs(status=JobStatus.COMPLETED)
                if len(jobs) == 5:
                    break
                await asyncio.sleep(0.1)

            # Max concurrent should not exceed 2
            assert running_count["max_seen"] <= 2
        finally:
            await job_queue.stop()

    async def test_job_ttl_set_on_completion(
        self, job_queue: RedisJobQueue, redis_client
    ):
        """Test that TTL is set on completed jobs."""

        async def dummy_handler() -> dict:
            return {"done": True}

        job_queue.register_handler("test", dummy_handler)
        await job_queue.start()

        try:
            job = await job_queue.submit("test", {})

            # Wait for completion
            for _ in range(50):
                updated = await job_queue.get_job(job.id)
                if updated and updated.status == JobStatus.COMPLETED:
                    break
                await asyncio.sleep(0.1)

            # Check TTL is set
            ttl = await redis_client.ttl(f"job:{job.id}")
            assert ttl > 0  # TTL should be positive
            assert ttl <= 3600  # 1 hour (job_ttl_hours=1)
        finally:
            await job_queue.stop()
