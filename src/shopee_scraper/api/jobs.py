"""Redis-backed background job queue for long-running scrape tasks."""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from shopee_scraper.api.enums import JobStatus
from shopee_scraper.exceptions import QueueFullError
from shopee_scraper.utils.config import JobQueueSettings
from shopee_scraper.utils.logging import get_logger


if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from redis.asyncio import Redis

logger = get_logger(__name__)


@dataclass
class Job:
    """Represents a background job."""

    id: str
    type: str
    params: dict[str, Any]
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    progress: int = 0  # 0-100
    retries: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert job to dictionary for API responses."""
        return {
            "id": self.id,
            "type": self.type,
            "status": self.status.value,
            "params": self.params,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "progress": self.progress,
            "result": self.result,
            "error": self.error,
            "retries": self.retries,
        }

    def to_json(self) -> str:
        """Serialize job to JSON string for Redis storage."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, data: str) -> Job:
        """Deserialize job from JSON string."""
        d = json.loads(data)
        return cls(
            id=d["id"],
            type=d["type"],
            params=d["params"],
            status=JobStatus(d["status"]),
            created_at=datetime.fromisoformat(d["created_at"]),
            started_at=(
                datetime.fromisoformat(d["started_at"]) if d.get("started_at") else None
            ),
            completed_at=(
                datetime.fromisoformat(d["completed_at"])
                if d.get("completed_at")
                else None
            ),
            result=d.get("result"),
            error=d.get("error"),
            progress=d.get("progress", 0),
            retries=d.get("retries", 0),
        )


# Redis key schema
_KEY_JOB = "job:{job_id}"  # String (JSON-serialized Job)
_KEY_QUEUE_PENDING = "job_queue:pending"  # List (job IDs, LPUSH/BRPOP)
_KEY_STATUS_SET = "jobs:status:{status}"  # Set (job IDs by status)
_KEY_ALL_JOBS = "jobs:all"  # Set (all job IDs)
_KEY_META = "job_queue:meta"  # Hash (queue stats)
_KEY_PUBSUB_JOB = "job:events:{job_id}"  # PubSub channel for job updates


class RedisJobQueue:
    """
    Redis-backed job queue with async workers.

    Features:
    - Persistent job storage via Redis
    - Bounded queue with configurable max size
    - Retry with exponential backoff
    - Handler timeout enforcement
    - Graceful shutdown with job recovery on restart
    - Periodic cleanup of expired jobs
    - Progress tracking
    """

    def __init__(self, redis: Redis, settings: JobQueueSettings) -> None:
        self._redis = redis
        self._settings = settings
        self._handlers: dict[
            str, Callable[..., Coroutine[Any, Any, dict[str, Any]]]
        ] = {}
        self._workers: list[asyncio.Task[None]] = []
        self._running = False
        self._cleanup_task: asyncio.Task[None] | None = None
        self._active_tasks: dict[str, asyncio.Task[Any]] = {}  # job_id -> task

    def register_handler(
        self,
        job_type: str,
        handler: Callable[..., Coroutine[Any, Any, dict[str, Any]]],
    ) -> None:
        """Register a handler for a job type."""
        self._handlers[job_type] = handler
        logger.info(f"Registered job handler: {job_type}")

    async def start(self) -> None:
        """Start workers, cleanup task, and recover interrupted jobs."""
        if self._running:
            return

        self._running = True

        # Recover jobs that were RUNNING when server crashed
        await self._recover_interrupted_jobs()

        # Start worker tasks
        for i in range(self._settings.max_concurrent):
            worker = asyncio.create_task(self._worker(i))
            self._workers.append(worker)

        # Start cleanup worker
        self._cleanup_task = asyncio.create_task(self._cleanup_worker())

        logger.info(f"Job queue started with {self._settings.max_concurrent} workers")

    async def stop(self) -> None:
        """Graceful shutdown: cancel workers, save running job state."""
        self._running = False

        # Cancel active job tasks
        for job_id, task in list(self._active_tasks.items()):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
            # Requeue the job so it can be picked up on restart
            await self._requeue_job(job_id)

        self._active_tasks.clear()

        # Cancel workers
        for worker in self._workers:
            worker.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._cleanup_task
            self._cleanup_task = None

        logger.info("Job queue stopped")

    async def submit(
        self,
        job_type: str,
        params: dict[str, Any],
    ) -> Job:
        """
        Submit a new job to the queue.

        Raises:
            ValueError: If job_type has no registered handler
            QueueFullError: If queue is at max capacity
        """
        if job_type not in self._handlers:
            raise ValueError(f"Unknown job type: {job_type}")

        # Check queue size
        queue_size = await self._redis.llen(_KEY_QUEUE_PENDING)
        if queue_size >= self._settings.max_queue_size:
            raise QueueFullError(
                f"Queue is full ({queue_size}/{self._settings.max_queue_size})"
            )

        job_id = str(uuid.uuid4())
        job = Job(id=job_id, type=job_type, params=params)

        # Pipeline all Redis operations for atomicity and performance
        pipe = self._redis.pipeline()
        pipe.set(_KEY_JOB.format(job_id=job_id), job.to_json())
        pipe.lpush(_KEY_QUEUE_PENDING, job_id)
        pipe.sadd(_KEY_ALL_JOBS, job_id)
        pipe.sadd(_KEY_STATUS_SET.format(status=JobStatus.PENDING.value), job_id)
        pipe.hincrby(_KEY_META, "total_submitted", 1)
        await pipe.execute()

        logger.info(f"Job submitted: {job_id} ({job_type})")
        return job

    async def get_job(self, job_id: str) -> Job | None:
        """Fetch job from Redis."""
        data = await self._redis.get(_KEY_JOB.format(job_id=job_id))
        if data is None:
            return None
        return Job.from_json(data)

    async def list_jobs(
        self,
        status: JobStatus | None = None,
        limit: int = 50,
    ) -> list[Job]:
        """List jobs, optionally filtered by status."""
        if status:
            # Get job IDs from status set
            job_ids = await self._redis.smembers(
                _KEY_STATUS_SET.format(status=status.value)
            )
        else:
            # Get all job IDs
            job_ids = await self._redis.smembers(_KEY_ALL_JOBS)

        # Fetch job data (pipeline for efficiency)
        jobs: list[Job] = []
        if job_ids:
            pipe = self._redis.pipeline()
            for job_id in job_ids:
                pipe.get(_KEY_JOB.format(job_id=job_id))
            results = await pipe.execute()

            for data in results:
                if data:
                    jobs.append(Job.from_json(data))

        # Sort by created_at descending
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a PENDING or RUNNING job."""
        job = await self.get_job(job_id)
        if not job:
            return False

        if job.status == JobStatus.PENDING:
            # Remove from pending queue (best-effort, LREM)
            await self._redis.lrem(_KEY_QUEUE_PENDING, 0, job_id)
            await self._transition_status(job, JobStatus.CANCELLED)
            job.completed_at = datetime.now(timezone.utc)
            await self._save_job(job)
            logger.info(f"Job cancelled (was pending): {job_id}")
            return True

        if job.status == JobStatus.RUNNING:
            # Cancel the active task if we have it
            task = self._active_tasks.get(job_id)
            if task:
                task.cancel()
            await self._transition_status(job, JobStatus.CANCELLED)
            job.completed_at = datetime.now(timezone.utc)
            await self._save_job(job)
            logger.info(f"Job cancelled (was running): {job_id}")
            return True

        return False

    async def update_progress(self, job_id: str, progress: int) -> None:
        """Update job progress (0-100) and publish event."""
        job = await self.get_job(job_id)
        if job and job.status == JobStatus.RUNNING:
            old_progress = job.progress
            job.progress = min(max(progress, 0), 100)
            await self._save_job(job)

            # Publish progress event for WebSocket subscribers
            await self._publish_job_event(
                job,
                "progress",
                {
                    "old_progress": old_progress,
                    "new_progress": job.progress,
                },
            )

    # -------------------------------------------------------------------------
    # Internal methods
    # -------------------------------------------------------------------------

    async def _save_job(self, job: Job) -> None:
        """Persist job to Redis with TTL for completed jobs."""
        key = _KEY_JOB.format(job_id=job.id)
        await self._redis.set(key, job.to_json())

        # Set TTL on completed/failed/cancelled jobs
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            ttl_seconds = self._settings.job_ttl_hours * 3600
            await self._redis.expire(key, ttl_seconds)

    async def _transition_status(self, job: Job, new_status: JobStatus) -> None:
        """Move job between status sets atomically and publish event."""
        old_status = job.status

        # Atomic status transition using pipeline
        pipe = self._redis.pipeline()
        pipe.srem(_KEY_STATUS_SET.format(status=old_status.value), job.id)
        pipe.sadd(_KEY_STATUS_SET.format(status=new_status.value), job.id)
        await pipe.execute()

        job.status = new_status

        # Publish status change event for WebSocket subscribers
        await self._publish_job_event(
            job,
            "status_changed",
            {
                "old_status": old_status.value,
                "new_status": new_status.value,
            },
        )

    async def _publish_job_event(
        self,
        job: Job,
        event_type: str,
        extra_data: dict[str, Any] | None = None,
    ) -> None:
        """Publish job event to Redis pub/sub channel."""
        event = {
            "event": event_type,
            "job_id": job.id,
            "status": job.status.value,
            "progress": job.progress,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if extra_data:
            event.update(extra_data)

        channel = _KEY_PUBSUB_JOB.format(job_id=job.id)
        try:
            await self._redis.publish(channel, json.dumps(event))
        except Exception as e:
            logger.debug(f"Failed to publish job event: {e}")

    async def _requeue_job(self, job_id: str) -> None:
        """Requeue a job back to pending state."""
        job = await self.get_job(job_id)
        if job:
            await self._transition_status(job, JobStatus.PENDING)
            job.started_at = None
            job.progress = 0
            await self._save_job(job)
            await self._redis.lpush(_KEY_QUEUE_PENDING, job_id)
            logger.info(f"Job requeued: {job_id}")

    async def _recover_interrupted_jobs(self) -> None:
        """On startup: requeue jobs that were RUNNING (server crashed)."""
        running_ids = await self._redis.smembers(
            _KEY_STATUS_SET.format(status=JobStatus.RUNNING.value)
        )
        for job_id in running_ids:
            await self._requeue_job(job_id)

        if running_ids:
            logger.info(f"Recovered {len(running_ids)} interrupted jobs")

    async def _worker(self, worker_id: int) -> None:
        """Worker loop: BRPOP from queue, process with timeout and retry."""
        logger.debug(f"Worker {worker_id} started")

        while self._running:
            try:
                # BRPOP with 1-second timeout to check _running flag
                result = await self._redis.brpop(_KEY_QUEUE_PENDING, timeout=1)
                if result is None:
                    continue

                _, job_id = result
                # job_id may be bytes if decode_responses is off, but we use decode_responses=True
                if isinstance(job_id, bytes):
                    job_id = job_id.decode()

                job = await self.get_job(job_id)
                if not job or job.status != JobStatus.PENDING:
                    continue

                await self._process_job(job, worker_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
                await asyncio.sleep(1)

        logger.debug(f"Worker {worker_id} stopped")

    async def _process_job(self, job: Job, worker_id: int) -> None:
        """Execute handler with timeout, retry on failure."""
        logger.info(f"Worker {worker_id} processing job: {job.id}")

        await self._transition_status(job, JobStatus.RUNNING)
        job.started_at = datetime.now(timezone.utc)
        await self._save_job(job)

        handler = self._handlers.get(job.type)
        if not handler:
            job.error = f"No handler for job type: {job.type}"
            await self._transition_status(job, JobStatus.FAILED)
            job.completed_at = datetime.now(timezone.utc)
            await self._save_job(job)
            return

        try:
            result = await self._execute_handler(job, handler)
            await self._mark_completed(job, result)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await self._handle_failure(job, e)
        finally:
            self._active_tasks.pop(job.id, None)

    async def _execute_handler(
        self,
        job: Job,
        handler: Callable[..., Coroutine[Any, Any, dict[str, Any]]],
    ) -> dict[str, Any]:
        """Execute handler with timeout, raising on failure."""
        task = asyncio.ensure_future(handler(**job.params))
        self._active_tasks[job.id] = task

        try:
            return await asyncio.wait_for(
                task, timeout=self._settings.handler_timeout_seconds
            )
        except asyncio.TimeoutError as exc:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
            raise TimeoutError(
                f"Job exceeded timeout of {self._settings.handler_timeout_seconds}s"
            ) from exc

    async def _mark_completed(self, job: Job, result: dict[str, Any]) -> None:
        """Mark job as successfully completed."""
        await self._transition_status(job, JobStatus.COMPLETED)
        job.result = result
        job.progress = 100
        job.completed_at = datetime.now(timezone.utc)
        await self._save_job(job)
        await self._redis.hincrby(_KEY_META, "total_completed", 1)

        # Publish completion event with result summary
        await self._publish_job_event(
            job,
            "completed",
            {
                "has_result": job.result is not None,
            },
        )
        logger.info(f"Job completed: {job.id}")

    async def _handle_failure(self, job: Job, error: Exception) -> None:
        """Handle job failure with retry logic."""
        job.retries += 1
        error_msg = str(error)

        if job.retries < self._settings.max_retries:
            delay = self._settings.retry_delay_seconds * (2 ** (job.retries - 1))
            logger.warning(
                f"Job {job.id} failed (attempt {job.retries}/{self._settings.max_retries}), "
                f"retrying in {delay}s: {error_msg}"
            )
            job.error = f"Retry {job.retries}: {error_msg}"
            await self._save_job(job)

            if delay > 0:
                await asyncio.sleep(delay)

            # Requeue for retry
            await self._transition_status(job, JobStatus.PENDING)
            job.started_at = None
            await self._save_job(job)
            await self._redis.lpush(_KEY_QUEUE_PENDING, job.id)
        else:
            await self._transition_status(job, JobStatus.FAILED)
            job.error = f"Failed after {job.retries} attempts: {error_msg}"
            job.completed_at = datetime.now(timezone.utc)
            await self._save_job(job)
            await self._redis.hincrby(_KEY_META, "total_failed", 1)
            logger.error(f"Job failed permanently: {job.id} - {error_msg}")

    async def _cleanup_worker(self) -> None:
        """Periodic cleanup of expired job references from sets."""
        while self._running:
            try:
                await asyncio.sleep(self._settings.cleanup_interval_seconds)
                await self._cleanup_expired_references()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup worker error: {e}")

    async def _cleanup_expired_references(self) -> None:
        """Remove references to jobs that have expired (TTL gone)."""
        all_ids = await self._redis.smembers(_KEY_ALL_JOBS)
        if not all_ids:
            return

        # Batch check which jobs still exist using pipeline
        check_pipe = self._redis.pipeline()
        job_ids_list = list(all_ids)
        for job_id in job_ids_list:
            check_pipe.exists(_KEY_JOB.format(job_id=job_id))
        exists_results = await check_pipe.execute()

        # Collect expired job IDs
        expired_ids = [
            job_id
            for job_id, exists in zip(job_ids_list, exists_results, strict=False)
            if not exists
        ]

        if not expired_ids:
            return

        # Batch remove expired references using pipeline
        cleanup_pipe = self._redis.pipeline()
        for job_id in expired_ids:
            cleanup_pipe.srem(_KEY_ALL_JOBS, job_id)
            for job_status in JobStatus:
                cleanup_pipe.srem(
                    _KEY_STATUS_SET.format(status=job_status.value), job_id
                )
        await cleanup_pipe.execute()

        logger.info(f"Cleaned up {len(expired_ids)} expired job references")


# Global job queue instance
_job_queue: RedisJobQueue | None = None


def get_job_queue() -> RedisJobQueue:
    """Get global job queue instance."""
    if _job_queue is None:
        raise RuntimeError("Job queue not initialized. Call setup_job_queue() first.")
    return _job_queue


async def setup_job_queue(
    redis: Redis,
    settings: JobQueueSettings,
    scraper_service: Any,
) -> RedisJobQueue:
    """
    Setup and start the Redis-backed job queue with handlers.

    Args:
        redis: Async Redis client
        settings: Job queue configuration
        scraper_service: ScraperService instance for job handlers

    Returns:
        Configured RedisJobQueue
    """
    global _job_queue  # noqa: PLW0603

    queue = RedisJobQueue(redis=redis, settings=settings)

    # Register job handlers
    async def scrape_list_handler(
        keyword: str,
        max_pages: int = 1,
        sort_by: str = "relevancy",
    ) -> dict[str, Any]:
        """Handler for scrape list jobs."""
        return await scraper_service.search_products(
            keyword=keyword,
            max_pages=max_pages,
            sort_by=sort_by,
            max_reviews=5,
        )

    async def scrape_list_and_details_handler(
        keyword: str,
        max_products: int = 10,
        include_reviews: bool = False,
    ) -> dict[str, Any]:
        """Handler for scrape list and details jobs."""
        max_reviews = 5 if include_reviews else 0
        return await scraper_service.get_products_batch(
            keyword=keyword,
            max_products=max_products,
            max_reviews=max_reviews,
        )

    # Extension-based handlers (force execution_mode="extension")
    async def scrape_via_extension_handler(
        keyword: str,
        max_pages: int = 1,
        sort_by: str = "relevancy",
    ) -> dict[str, Any]:
        """Handler for extension-based search jobs."""
        return await scraper_service.search_products(
            keyword=keyword,
            max_pages=max_pages,
            sort_by=sort_by,
            max_reviews=0,
            execution_mode="extension",
        )

    async def scrape_product_via_extension_handler(
        shop_id: int,
        item_id: int,
    ) -> dict[str, Any]:
        """Handler for extension-based product detail jobs."""
        result = await scraper_service.get_product(
            shop_id=shop_id,
            item_id=item_id,
            execution_mode="extension",
        )
        return result or {"error": "Product not found"}

    queue.register_handler("scrape_list", scrape_list_handler)
    queue.register_handler("scrape_list_and_details", scrape_list_and_details_handler)
    queue.register_handler("scrape_via_extension", scrape_via_extension_handler)
    queue.register_handler(
        "scrape_product_via_extension", scrape_product_via_extension_handler
    )

    # Start the queue
    await queue.start()

    _job_queue = queue
    return queue


async def cleanup_job_queue() -> None:
    """Stop and cleanup job queue."""
    global _job_queue  # noqa: PLW0603
    if _job_queue:
        await _job_queue.stop()
        _job_queue = None


def get_job_pubsub_channel(job_id: str) -> str:
    """Get the Redis pub/sub channel name for a job's events."""
    return _KEY_PUBSUB_JOB.format(job_id=job_id)
