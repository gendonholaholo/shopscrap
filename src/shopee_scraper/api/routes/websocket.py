"""WebSocket routes for real-time job status updates."""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import TYPE_CHECKING

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from shopee_scraper.api.dependencies import get_redis
from shopee_scraper.api.jobs import JobStatus, get_job_pubsub_channel, get_job_queue
from shopee_scraper.utils.logging import get_logger


if TYPE_CHECKING:
    from redis.asyncio.client import PubSub

    from shopee_scraper.api.jobs import Job, RedisJobQueue

logger = get_logger(__name__)

router = APIRouter(prefix="/ws", tags=["WebSocket"])


class ConnectionManager:
    """Manages WebSocket connections for job status updates."""

    def __init__(self) -> None:
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, job_id: str) -> None:
        """Accept WebSocket connection and register for job updates."""
        await websocket.accept()
        if job_id not in self.active_connections:
            self.active_connections[job_id] = []
        self.active_connections[job_id].append(websocket)
        logger.debug(f"WebSocket connected for job: {job_id}")

    def disconnect(self, websocket: WebSocket, job_id: str) -> None:
        """Remove WebSocket connection."""
        if job_id in self.active_connections:
            if websocket in self.active_connections[job_id]:
                self.active_connections[job_id].remove(websocket)
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]
        logger.debug(f"WebSocket disconnected for job: {job_id}")

    async def send_event(self, job_id: str, event: dict) -> None:
        """Send event to all connections watching a job."""
        if job_id in self.active_connections:
            dead_connections = []
            for websocket in self.active_connections[job_id]:
                try:
                    await websocket.send_json(event)
                except Exception:
                    dead_connections.append(websocket)

            # Clean up dead connections
            for ws in dead_connections:
                self.disconnect(ws, job_id)


manager = ConnectionManager()


# Terminal job statuses that indicate job completion
_TERMINAL_STATUSES = (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)
_TERMINAL_STATUS_VALUES = ("completed", "failed", "cancelled")


async def _send_job_not_found(websocket: WebSocket, job_id: str) -> None:
    """Send error for non-existent job and close connection."""
    await websocket.send_json({"event": "error", "message": f"Job not found: {job_id}"})
    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)


async def _send_initial_status(websocket: WebSocket, job: Job) -> None:
    """Send initial job status after connection."""
    await websocket.send_json(
        {
            "event": "connected",
            "job_id": job.id,
            "status": job.status.value,
            "progress": job.progress,
            "message": "Connected to job status stream",
        }
    )


async def _send_terminal_status(websocket: WebSocket, job: Job, msg: str = "") -> None:
    """Send final status for a terminal job and close connection."""
    await websocket.send_json(
        {
            "event": "final_status",
            "job_id": job.id,
            "status": job.status.value,
            "progress": job.progress,
            "result": job.result,
            "error": job.error,
            "message": msg or "Job completed",
        }
    )
    await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)


async def _process_pubsub_message(
    message: dict,
    websocket: WebSocket,
    queue: RedisJobQueue,
    job_id: str,
) -> bool:
    """Process a pub/sub message. Returns True if job reached terminal state."""
    if message is None or message["type"] != "message":
        return False

    data = message["data"]
    if isinstance(data, bytes):
        data = data.decode()
    event = json.loads(data)

    await websocket.send_json(event)

    if event.get("status") in _TERMINAL_STATUS_VALUES:
        final_job = await queue.get_job(job_id)
        if final_job:
            await _send_terminal_status(websocket, final_job)
        return True

    return False


async def _handle_client_ping(websocket: WebSocket) -> None:
    """Check for and respond to client ping messages."""
    with contextlib.suppress(asyncio.TimeoutError):
        client_msg = await asyncio.wait_for(websocket.receive_text(), timeout=0.01)
        if client_msg == "ping":
            await websocket.send_json({"event": "pong"})


async def _listen_for_events(
    websocket: WebSocket,
    pubsub: PubSub,
    queue: RedisJobQueue,
    job_id: str,
    channel: str,
) -> None:
    """Main event loop listening for pub/sub messages."""
    try:
        while True:
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0),
                    timeout=30.0,
                )

                if await _process_pubsub_message(message, websocket, queue, job_id):
                    return

                await _handle_client_ping(websocket)

            except asyncio.TimeoutError:
                await websocket.send_json({"event": "ping"})

    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()


@router.websocket("/jobs/{job_id}")
async def job_status_websocket(websocket: WebSocket, job_id: str) -> None:
    """
    WebSocket endpoint for real-time job status updates.

    Connect to receive live updates for a specific job including:
    - status_changed: When job status changes (pending -> running -> completed/failed)
    - progress: When job progress updates
    - completed: When job finishes successfully
    - error: When job fails

    Example client usage (JavaScript):
    ```javascript
    const ws = new WebSocket('ws://localhost:8000/api/v1/ws/jobs/{job_id}');
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log('Job update:', data);
        if (data.status === 'completed' || data.status === 'failed') {
            ws.close();
        }
    };
    ```
    """
    await manager.connect(websocket, job_id)

    try:
        redis = await get_redis()
        queue = get_job_queue()
        job = await queue.get_job(job_id)

        if job is None:
            await _send_job_not_found(websocket, job_id)
            return

        await _send_initial_status(websocket, job)

        if job.status in _TERMINAL_STATUSES:
            await _send_terminal_status(websocket, job, "Job already in terminal state")
            return

        channel = get_job_pubsub_channel(job_id)
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)

        await _listen_for_events(websocket, pubsub, queue, job_id, channel)

    except WebSocketDisconnect:
        logger.debug(f"WebSocket client disconnected for job: {job_id}")
    except Exception as e:
        logger.error(f"WebSocket error for job {job_id}: {e}")
        with contextlib.suppress(Exception):
            await websocket.send_json({"event": "error", "message": str(e)})
    finally:
        manager.disconnect(websocket, job_id)
