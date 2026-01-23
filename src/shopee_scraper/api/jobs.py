"""Background job queue for long-running scrape tasks."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from shopee_scraper.utils.logging import get_logger


if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

logger = get_logger(__name__)


class JobStatus(str, Enum):
    """Job status enum."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    """Represents a background job."""

    id: str
    type: str
    params: dict[str, Any]
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    progress: int = 0  # 0-100

    def to_dict(self) -> dict[str, Any]:
        """Convert job to dictionary."""
        return {
            "id": self.id,
            "type": self.type,
            "status": self.status.value,
            "params": self.params,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "progress": self.progress,
            "result": self.result,
            "error": self.error,
        }


class JobQueue:
    """
    Simple in-memory job queue for background tasks.

    For production, consider using Celery with Redis/RabbitMQ.
    """

    def __init__(self, max_concurrent: int = 3) -> None:
        """
        Initialize job queue.

        Args:
            max_concurrent: Maximum concurrent jobs
        """
        self.max_concurrent = max_concurrent
        self._jobs: dict[str, Job] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._handlers: dict[
            str, Callable[..., Coroutine[Any, Any, dict[str, Any]]]
        ] = {}
        self._workers: list[asyncio.Task[None]] = []
        self._running = False

    def register_handler(
        self,
        job_type: str,
        handler: Callable[..., Coroutine[Any, Any, dict[str, Any]]],
    ) -> None:
        """Register a handler for a job type."""
        self._handlers[job_type] = handler
        logger.info(f"Registered job handler: {job_type}")

    async def start(self) -> None:
        """Start the job queue workers."""
        if self._running:
            return

        self._running = True
        for i in range(self.max_concurrent):
            worker = asyncio.create_task(self._worker(i))
            self._workers.append(worker)

        logger.info(f"Job queue started with {self.max_concurrent} workers")

    async def stop(self) -> None:
        """Stop the job queue workers."""
        self._running = False

        # Cancel all workers
        for worker in self._workers:
            worker.cancel()

        # Wait for workers to finish
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)

        self._workers.clear()
        logger.info("Job queue stopped")

    async def submit(
        self,
        job_type: str,
        params: dict[str, Any],
    ) -> Job:
        """
        Submit a new job to the queue.

        Args:
            job_type: Type of job (must have registered handler)
            params: Job parameters

        Returns:
            Created job
        """
        if job_type not in self._handlers:
            raise ValueError(f"Unknown job type: {job_type}")

        job_id = str(uuid.uuid4())
        job = Job(
            id=job_id,
            type=job_type,
            params=params,
        )

        self._jobs[job_id] = job
        await self._queue.put(job_id)

        logger.info(f"Job submitted: {job_id} ({job_type})")
        return job

    def get_job(self, job_id: str) -> Job | None:
        """Get job by ID."""
        return self._jobs.get(job_id)

    def list_jobs(
        self,
        status: JobStatus | None = None,
        limit: int = 100,
    ) -> list[Job]:
        """List jobs, optionally filtered by status."""
        jobs = list(self._jobs.values())

        if status:
            jobs = [j for j in jobs if j.status == status]

        # Sort by created_at descending
        jobs.sort(key=lambda j: j.created_at, reverse=True)

        return jobs[:limit]

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending job."""
        job = self._jobs.get(job_id)
        if not job:
            return False

        if job.status == JobStatus.PENDING:
            job.status = JobStatus.CANCELLED
            job.completed_at = datetime.utcnow()
            logger.info(f"Job cancelled: {job_id}")
            return True

        return False

    def cleanup_old_jobs(self, max_age_hours: int = 24) -> int:
        """Remove old completed/failed jobs."""
        cutoff = datetime.utcnow()
        removed = 0

        for job_id, job in list(self._jobs.items()):
            is_finished = job.status in (
                JobStatus.COMPLETED,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
            )
            if is_finished and job.completed_at:
                age = (cutoff - job.completed_at).total_seconds() / 3600
                if age > max_age_hours:
                    del self._jobs[job_id]
                    removed += 1

        if removed:
            logger.info(f"Cleaned up {removed} old jobs")

        return removed

    async def _worker(self, worker_id: int) -> None:
        """Worker coroutine that processes jobs."""
        logger.debug(f"Worker {worker_id} started")

        while self._running:
            try:
                # Wait for a job with timeout
                try:
                    job_id = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=1.0,
                    )
                except asyncio.TimeoutError:
                    continue

                job = self._jobs.get(job_id)
                if not job or job.status != JobStatus.PENDING:
                    continue

                # Process the job
                await self._process_job(job, worker_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")

        logger.debug(f"Worker {worker_id} stopped")

    async def _process_job(self, job: Job, worker_id: int) -> None:
        """Process a single job."""
        logger.info(f"Worker {worker_id} processing job: {job.id}")

        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()

        try:
            handler = self._handlers[job.type]
            result = await handler(**job.params)

            job.status = JobStatus.COMPLETED
            job.result = result
            job.progress = 100

            logger.info(f"Job completed: {job.id}")

        except Exception as e:
            job.status = JobStatus.FAILED
            job.error = str(e)
            logger.error(f"Job failed: {job.id} - {e}")

        finally:
            job.completed_at = datetime.utcnow()


# Global job queue instance
_job_queue: JobQueue | None = None


def get_job_queue() -> JobQueue:
    """Get or create global job queue."""
    global _job_queue  # noqa: PLW0603
    if _job_queue is None:
        _job_queue = JobQueue(max_concurrent=3)
    return _job_queue


async def setup_job_queue(scraper_service: Any) -> JobQueue:
    """
    Setup and start the job queue with handlers.

    Args:
        scraper_service: ScraperService instance for job handlers

    Returns:
        Configured JobQueue
    """
    queue = get_job_queue()

    # Register job handlers
    async def scrape_list_handler(
        keyword: str,
        max_pages: int = 1,
        sort_by: str = "relevancy",
    ) -> dict[str, Any]:
        """Handler for scrape list jobs - returns ExportOutput format."""
        # search_products now returns ExportOutput-compatible dict
        return await scraper_service.search_products(
            keyword=keyword,
            max_pages=max_pages,
            sort_by=sort_by,
            max_reviews=5,  # Default reviews per product
        )

    async def scrape_list_and_details_handler(
        keyword: str,
        max_products: int = 10,
        include_reviews: bool = False,
    ) -> dict[str, Any]:
        """Handler for scrape list and details jobs - returns ExportOutput format."""
        # get_products_batch returns ExportOutput-compatible dict
        # Reviews are already included via scraper.search()
        max_reviews = 5 if include_reviews else 0
        return await scraper_service.get_products_batch(
            keyword=keyword,
            max_products=max_products,
            max_reviews=max_reviews,
        )

    queue.register_handler("scrape_list", scrape_list_handler)
    queue.register_handler("scrape_list_and_details", scrape_list_and_details_handler)

    # Start the queue
    await queue.start()

    return queue


async def cleanup_job_queue() -> None:
    """Stop and cleanup job queue."""
    global _job_queue  # noqa: PLW0603
    if _job_queue:
        await _job_queue.stop()
        _job_queue = None
