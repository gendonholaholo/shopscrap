"""Unit tests for API job queue."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest

from shopee_scraper.api.jobs import Job, JobQueue, JobStatus


class TestJob:
    """Tests for Job dataclass."""

    def test_job_creation(self) -> None:
        """Test basic job creation."""
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

    def test_job_to_dict(self) -> None:
        """Test job serialization to dict."""
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

    def test_job_status_transitions(self) -> None:
        """Test job status transitions."""
        job = Job(id="test", type="test", params={})

        assert job.status == JobStatus.PENDING

        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        assert job.status == JobStatus.RUNNING

        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.utcnow()
        job.result = {"data": "test"}
        assert job.status == JobStatus.COMPLETED


class TestJobQueue:
    """Tests for JobQueue class."""

    @pytest.fixture
    def queue(self) -> JobQueue:
        """Create a test queue."""
        return JobQueue(max_concurrent=2)

    @pytest.mark.asyncio
    async def test_register_handler(self, queue: JobQueue) -> None:
        """Test handler registration."""

        async def dummy_handler(keyword: str) -> dict:
            return {"keyword": keyword}

        queue.register_handler("test_job", dummy_handler)
        assert "test_job" in queue._handlers

    @pytest.mark.asyncio
    async def test_submit_job(self, queue: JobQueue) -> None:
        """Test job submission."""

        async def dummy_handler(keyword: str) -> dict:
            return {"keyword": keyword}

        queue.register_handler("search", dummy_handler)

        job = await queue.submit("search", {"keyword": "test"})

        assert job.id is not None
        assert job.type == "search"
        assert job.status == JobStatus.PENDING
        assert job.params == {"keyword": "test"}

    @pytest.mark.asyncio
    async def test_submit_unknown_job_type(self, queue: JobQueue) -> None:
        """Test submitting unknown job type raises error."""
        with pytest.raises(ValueError, match="Unknown job type"):
            await queue.submit("unknown_type", {})

    @pytest.mark.asyncio
    async def test_get_job(self, queue: JobQueue) -> None:
        """Test getting job by ID."""

        async def dummy_handler() -> dict:
            return {}

        queue.register_handler("test", dummy_handler)

        job = await queue.submit("test", {})
        retrieved = queue.get_job(job.id)

        assert retrieved is not None
        assert retrieved.id == job.id

    def test_get_nonexistent_job(self, queue: JobQueue) -> None:
        """Test getting non-existent job returns None."""
        assert queue.get_job("nonexistent") is None

    @pytest.mark.asyncio
    async def test_list_jobs(self, queue: JobQueue) -> None:
        """Test listing jobs."""

        async def dummy_handler() -> dict:
            return {}

        queue.register_handler("test", dummy_handler)

        # Submit multiple jobs
        await queue.submit("test", {})
        await queue.submit("test", {})
        await queue.submit("test", {})

        jobs = queue.list_jobs()
        assert len(jobs) == 3

    @pytest.mark.asyncio
    async def test_list_jobs_with_filter(self, queue: JobQueue) -> None:
        """Test listing jobs with status filter."""

        async def dummy_handler() -> dict:
            return {}

        queue.register_handler("test", dummy_handler)

        job1 = await queue.submit("test", {})
        await queue.submit("test", {})

        # Mark one as completed
        job1.status = JobStatus.COMPLETED

        pending_jobs = queue.list_jobs(status=JobStatus.PENDING)
        completed_jobs = queue.list_jobs(status=JobStatus.COMPLETED)

        assert len(pending_jobs) == 1
        assert len(completed_jobs) == 1

    @pytest.mark.asyncio
    async def test_cancel_pending_job(self, queue: JobQueue) -> None:
        """Test cancelling a pending job."""

        async def dummy_handler() -> dict:
            return {}

        queue.register_handler("test", dummy_handler)

        job = await queue.submit("test", {})
        assert queue.cancel_job(job.id) is True
        assert job.status == JobStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_running_job_fails(self, queue: JobQueue) -> None:
        """Test that cancelling running job fails."""

        async def dummy_handler() -> dict:
            return {}

        queue.register_handler("test", dummy_handler)

        job = await queue.submit("test", {})
        job.status = JobStatus.RUNNING

        assert queue.cancel_job(job.id) is False

    def test_cancel_nonexistent_job(self, queue: JobQueue) -> None:
        """Test cancelling non-existent job returns False."""
        assert queue.cancel_job("nonexistent") is False

    @pytest.mark.asyncio
    async def test_cleanup_old_jobs(self, queue: JobQueue) -> None:
        """Test cleanup of old completed jobs."""

        async def dummy_handler() -> dict:
            return {}

        queue.register_handler("test", dummy_handler)

        # Create an old completed job
        old_job = await queue.submit("test", {})
        old_job.status = JobStatus.COMPLETED
        old_job.completed_at = datetime.utcnow() - timedelta(hours=25)

        # Create a recent completed job
        recent_job = await queue.submit("test", {})
        recent_job.status = JobStatus.COMPLETED
        recent_job.completed_at = datetime.utcnow()

        removed = queue.cleanup_old_jobs(max_age_hours=24)

        assert removed == 1
        assert queue.get_job(old_job.id) is None
        assert queue.get_job(recent_job.id) is not None

    @pytest.mark.asyncio
    async def test_job_processing(self, queue: JobQueue) -> None:
        """Test that jobs are processed by workers."""
        result_holder = {"processed": False}

        async def test_handler(value: str) -> dict:
            result_holder["processed"] = True
            return {"value": value}

        queue.register_handler("test", test_handler)

        # Start the queue
        await queue.start()

        try:
            # Submit a job
            job = await queue.submit("test", {"value": "hello"})

            # Wait for processing
            for _ in range(50):  # Max 5 seconds
                if job.status == JobStatus.COMPLETED:
                    break
                await asyncio.sleep(0.1)

            assert result_holder["processed"] is True
            assert job.status == JobStatus.COMPLETED
            assert job.result == {"value": "hello"}

        finally:
            await queue.stop()

    @pytest.mark.asyncio
    async def test_job_failure_handling(self, queue: JobQueue) -> None:
        """Test that job failures are handled properly."""

        async def failing_handler() -> dict:
            raise ValueError("Test error")

        queue.register_handler("failing", failing_handler)

        await queue.start()

        try:
            job = await queue.submit("failing", {})

            # Wait for processing
            for _ in range(50):
                if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                    break
                await asyncio.sleep(0.1)

            assert job.status == JobStatus.FAILED
            assert "Test error" in job.error

        finally:
            await queue.stop()
