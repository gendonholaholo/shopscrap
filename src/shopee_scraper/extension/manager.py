"""Extension manager for Chrome Extension connections and task dispatch."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from shopee_scraper.extension.protocol import (
    MessageType,
    RegisterPayload,
    TaskResultPayload,
    TaskType,
    WebSocketMessage,
)
from shopee_scraper.utils.logging import get_logger


if TYPE_CHECKING:
    from fastapi import WebSocket

logger = get_logger(__name__)


@dataclass
class ExtensionConnection:
    """Represents a connected Chrome Extension instance."""

    websocket: WebSocket
    extension_id: str
    user_agent: str = ""
    version: str = "1.0"
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_heartbeat: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ExtensionManager:
    """Manages Chrome Extension connections and task dispatch.

    Responsibilities:
    - Registry of connected extensions
    - Task dispatch to extensions with Future-based result waiting
    - Heartbeat monitoring and dead connection cleanup
    """

    def __init__(
        self,
        task_timeout: int = 300,
        heartbeat_timeout: int = 90,
    ) -> None:
        self._extensions: dict[str, ExtensionConnection] = {}
        self._pending_tasks: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._task_timeout = task_timeout
        self._heartbeat_timeout = heartbeat_timeout
        self._heartbeat_check_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the heartbeat checker background task."""
        self._heartbeat_check_task = asyncio.create_task(self._heartbeat_checker())
        logger.info("ExtensionManager started")

    async def stop(self) -> None:
        """Stop the manager and cleanup."""
        if self._heartbeat_check_task:
            self._heartbeat_check_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_check_task
            self._heartbeat_check_task = None

        # Fail all pending tasks
        for _task_id, future in list(self._pending_tasks.items()):
            if not future.done():
                future.set_exception(ConnectionError("ExtensionManager shutting down"))
        self._pending_tasks.clear()
        self._extensions.clear()
        logger.info("ExtensionManager stopped")

    def register(
        self,
        websocket: WebSocket,
        payload: RegisterPayload,
    ) -> None:
        """Register a new extension connection."""
        conn = ExtensionConnection(
            websocket=websocket,
            extension_id=payload.extension_id,
            user_agent=payload.user_agent,
            version=payload.version,
        )
        self._extensions[payload.extension_id] = conn
        logger.info(
            "Extension registered",
            extension_id=payload.extension_id,
            user_agent=payload.user_agent[:50] if payload.user_agent else "",
        )

    async def unregister(self, extension_id: str) -> None:
        """Unregister an extension and fail its pending tasks."""
        conn = self._extensions.pop(extension_id, None)
        if conn is None:
            return

        # Fail pending tasks that were assigned to this extension
        failed_tasks = []
        for task_id, future in list(self._pending_tasks.items()):
            if not future.done():
                future.set_exception(
                    ConnectionError(f"Extension {extension_id} disconnected")
                )
                failed_tasks.append(task_id)

        for task_id in failed_tasks:
            self._pending_tasks.pop(task_id, None)

        logger.info(
            "Extension unregistered",
            extension_id=extension_id,
            failed_tasks=len(failed_tasks),
        )

    def has_available(self) -> bool:
        """Check if any extension is connected."""
        return len(self._extensions) > 0

    def get_connections(self) -> list[dict[str, Any]]:
        """Get list of connected extensions for status display."""
        return [
            {
                "extension_id": conn.extension_id,
                "user_agent": conn.user_agent,
                "connected_at": conn.connected_at.isoformat(),
                "last_heartbeat": conn.last_heartbeat.isoformat(),
            }
            for conn in self._extensions.values()
        ]

    async def dispatch_task(
        self,
        task_type: TaskType,
        params: dict[str, Any],
        extension_id: str | None = None,
    ) -> str:
        """Dispatch a task to an extension.

        Args:
            task_type: Type of scraping task
            params: Task parameters
            extension_id: Specific extension to target (or None for any)

        Returns:
            task_id for tracking

        Raises:
            ConnectionError: If no extension is available
        """
        conn = self._get_connection(extension_id)
        if conn is None:
            raise ConnectionError("No extension available for task dispatch")

        task_id = str(uuid.uuid4())

        # Create future for result
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending_tasks[task_id] = future

        # Send task to extension
        message = WebSocketMessage.create(
            MessageType.TASK,
            task_id=task_id,
            task_type=task_type.value,
            params=params,
        )

        try:
            await conn.websocket.send_text(message.to_json_str())
        except Exception as e:
            self._pending_tasks.pop(task_id, None)
            raise ConnectionError(f"Failed to send task to extension: {e}") from e

        logger.info(
            "Task dispatched",
            task_id=task_id,
            task_type=task_type.value,
            extension_id=conn.extension_id,
        )
        return task_id

    async def wait_for_result(
        self,
        task_id: str,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Wait for a task result.

        Args:
            task_id: Task ID to wait for
            timeout: Override default timeout (seconds)

        Returns:
            Raw result data from extension

        Raises:
            TimeoutError: If task exceeds timeout
            ConnectionError: If extension disconnects
            KeyError: If task_id is unknown
        """
        future = self._pending_tasks.get(task_id)
        if future is None:
            raise KeyError(f"Unknown task_id: {task_id}")

        effective_timeout = timeout or self._task_timeout

        try:
            return await asyncio.wait_for(future, timeout=effective_timeout)
        except asyncio.TimeoutError:
            self._pending_tasks.pop(task_id, None)
            raise TimeoutError(
                f"Task {task_id} timed out after {effective_timeout}s"
            ) from None

    async def handle_message(
        self,
        extension_id: str,
        message: WebSocketMessage,
    ) -> None:
        """Route an incoming message from an extension."""
        handlers = {
            MessageType.HEARTBEAT: self._handle_heartbeat,
            MessageType.TASK_RESULT: self._handle_task_result,
            MessageType.TASK_ERROR: self._handle_task_error,
            MessageType.PROGRESS: self._handle_progress,
        }

        handler = handlers.get(message.type)
        if handler is None:
            logger.warning(
                "Unknown message type",
                extension_id=extension_id,
                message_type=message.type,
            )
            return

        await handler(extension_id, message.payload)

    # -------------------------------------------------------------------------
    # Message handlers
    # -------------------------------------------------------------------------

    async def _handle_heartbeat(
        self, extension_id: str, _payload: dict[str, Any]
    ) -> None:
        conn = self._extensions.get(extension_id)
        if conn:
            conn.last_heartbeat = datetime.now(timezone.utc)

        # Send pong
        pong = WebSocketMessage.create(MessageType.PONG)
        if conn:
            with contextlib.suppress(Exception):
                await conn.websocket.send_text(pong.to_json_str())

    async def _handle_task_result(
        self, extension_id: str, payload: dict[str, Any]
    ) -> None:
        result = TaskResultPayload(**payload)
        future = self._pending_tasks.pop(result.task_id, None)
        if future and not future.done():
            future.set_result(result.raw_data)
            logger.info(
                "Task result received",
                task_id=result.task_id,
                extension_id=extension_id,
            )
        else:
            logger.warning(
                "Received result for unknown/completed task",
                task_id=result.task_id,
            )

    async def _handle_task_error(
        self, extension_id: str, payload: dict[str, Any]
    ) -> None:
        task_id = payload.get("task_id", "")
        error = payload.get("error", "Unknown error")
        future = self._pending_tasks.pop(task_id, None)
        if future and not future.done():
            future.set_exception(RuntimeError(f"Extension task failed: {error}"))
            logger.warning(
                "Task error received",
                task_id=task_id,
                error=error,
                extension_id=extension_id,
            )

    async def _handle_progress(
        self, extension_id: str, payload: dict[str, Any]
    ) -> None:
        # Progress is informational — could be forwarded to job queue
        logger.debug(
            "Task progress",
            task_id=payload.get("task_id"),
            percent=payload.get("percent"),
            extension_id=extension_id,
        )

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _get_connection(
        self, extension_id: str | None = None
    ) -> ExtensionConnection | None:
        """Get a specific connection or the first available one."""
        if extension_id:
            return self._extensions.get(extension_id)
        # Return first connected extension
        if self._extensions:
            return next(iter(self._extensions.values()))
        return None

    async def _heartbeat_checker(self) -> None:
        """Periodically check for dead connections."""
        while True:
            try:
                await asyncio.sleep(30)
                now = datetime.now(timezone.utc)
                dead_ids = []

                for ext_id, conn in self._extensions.items():
                    elapsed = (now - conn.last_heartbeat).total_seconds()
                    if elapsed > self._heartbeat_timeout:
                        dead_ids.append(ext_id)
                        logger.warning(
                            "Extension heartbeat timeout",
                            extension_id=ext_id,
                            elapsed_seconds=elapsed,
                        )

                for ext_id in dead_ids:
                    await self.unregister(ext_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat checker error: {e}")


# Module-level singleton
_manager: ExtensionManager | None = None


def get_extension_manager() -> ExtensionManager:
    """Get the global ExtensionManager instance."""
    if _manager is None:
        raise RuntimeError(
            "ExtensionManager not initialized. Call init_extension_manager() first."
        )
    return _manager


async def init_extension_manager(
    task_timeout: int = 300,
    heartbeat_timeout: int = 90,
) -> ExtensionManager:
    """Initialize and start the global ExtensionManager."""
    global _manager  # noqa: PLW0603
    _manager = ExtensionManager(
        task_timeout=task_timeout,
        heartbeat_timeout=heartbeat_timeout,
    )
    await _manager.start()
    return _manager


async def cleanup_extension_manager() -> None:
    """Stop and cleanup the global ExtensionManager."""
    global _manager  # noqa: PLW0603
    if _manager:
        await _manager.stop()
        _manager = None
