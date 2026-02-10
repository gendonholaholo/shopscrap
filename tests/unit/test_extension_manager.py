"""Unit tests for extension manager."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from shopee_scraper.extension.manager import ExtensionManager
from shopee_scraper.extension.protocol import (
    MessageType,
    RegisterPayload,
    TaskType,
    WebSocketMessage,
)


@pytest.fixture
def manager() -> ExtensionManager:
    """Create an ExtensionManager without starting background tasks."""
    return ExtensionManager(task_timeout=5, heartbeat_timeout=10)


@pytest.fixture
def mock_websocket() -> MagicMock:
    """Create a mock WebSocket."""
    ws = MagicMock()
    ws.send_text = AsyncMock()
    return ws


@pytest.fixture
def register_payload() -> RegisterPayload:
    return RegisterPayload(
        extension_id="test-ext-001",
        user_agent="Mozilla/5.0 Test",
        version="1.0",
    )


class TestRegistration:
    """Tests for extension registration/unregistration."""

    def test_register(
        self,
        manager: ExtensionManager,
        mock_websocket: MagicMock,
        register_payload: RegisterPayload,
    ) -> None:
        manager.register(mock_websocket, register_payload)
        assert manager.has_available()
        connections = manager.get_connections()
        assert len(connections) == 1
        assert connections[0]["extension_id"] == "test-ext-001"

    async def test_unregister(
        self,
        manager: ExtensionManager,
        mock_websocket: MagicMock,
        register_payload: RegisterPayload,
    ) -> None:
        manager.register(mock_websocket, register_payload)
        assert manager.has_available()

        await manager.unregister("test-ext-001")
        assert not manager.has_available()
        assert manager.get_connections() == []

    async def test_unregister_unknown(self, manager: ExtensionManager) -> None:
        """Unregistering unknown extension should be a no-op."""
        await manager.unregister("nonexistent")
        assert not manager.has_available()

    def test_has_available_empty(self, manager: ExtensionManager) -> None:
        assert not manager.has_available()


class TestTaskDispatch:
    """Tests for task dispatch and result handling."""

    async def test_dispatch_task(
        self,
        manager: ExtensionManager,
        mock_websocket: MagicMock,
        register_payload: RegisterPayload,
    ) -> None:
        manager.register(mock_websocket, register_payload)

        task_id = await manager.dispatch_task(
            task_type=TaskType.SEARCH,
            params={"keyword": "laptop"},
        )

        assert task_id  # non-empty string
        mock_websocket.send_text.assert_called_once()

        # Verify the sent message
        import json

        sent_data = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_data["type"] == "task"
        assert sent_data["payload"]["task_id"] == task_id
        assert sent_data["payload"]["task_type"] == "search"

    async def test_dispatch_no_extension(self, manager: ExtensionManager) -> None:
        """Should raise when no extension connected."""
        with pytest.raises(ConnectionError, match="No extension available"):
            await manager.dispatch_task(
                task_type=TaskType.SEARCH,
                params={"keyword": "test"},
            )

    async def test_dispatch_and_wait_result(
        self,
        manager: ExtensionManager,
        mock_websocket: MagicMock,
        register_payload: RegisterPayload,
    ) -> None:
        manager.register(mock_websocket, register_payload)

        task_id = await manager.dispatch_task(
            task_type=TaskType.PRODUCT,
            params={"shopId": 123, "itemId": 456},
        )

        # Simulate result coming back
        result_data = {"data": {"item": {"name": "Test Product"}}}
        result_msg = WebSocketMessage.create(
            MessageType.TASK_RESULT,
            task_id=task_id,
            raw_data=result_data,
        )

        # Handle result in background, then wait
        async def send_result():
            await asyncio.sleep(0.1)
            await manager.handle_message("test-ext-001", result_msg)

        task = asyncio.create_task(send_result())
        result = await manager.wait_for_result(task_id, timeout=5)
        assert result == result_data
        await task

    async def test_wait_timeout(
        self,
        manager: ExtensionManager,
        mock_websocket: MagicMock,
        register_payload: RegisterPayload,
    ) -> None:
        manager.register(mock_websocket, register_payload)

        task_id = await manager.dispatch_task(
            task_type=TaskType.SEARCH,
            params={"keyword": "test"},
        )

        with pytest.raises(TimeoutError):
            await manager.wait_for_result(task_id, timeout=0.1)

    async def test_wait_unknown_task(self, manager: ExtensionManager) -> None:
        with pytest.raises(KeyError):
            await manager.wait_for_result("nonexistent-task")


class TestMessageHandling:
    """Tests for incoming message handling."""

    async def test_handle_heartbeat(
        self,
        manager: ExtensionManager,
        mock_websocket: MagicMock,
        register_payload: RegisterPayload,
    ) -> None:
        manager.register(mock_websocket, register_payload)

        msg = WebSocketMessage.create(
            MessageType.HEARTBEAT, extension_id="test-ext-001"
        )
        await manager.handle_message("test-ext-001", msg)

        # Should have sent pong
        assert mock_websocket.send_text.call_count == 1

    async def test_handle_task_error(
        self,
        manager: ExtensionManager,
        mock_websocket: MagicMock,
        register_payload: RegisterPayload,
    ) -> None:
        manager.register(mock_websocket, register_payload)

        task_id = await manager.dispatch_task(
            task_type=TaskType.SEARCH,
            params={"keyword": "test"},
        )

        # Send error
        error_msg = WebSocketMessage.create(
            MessageType.TASK_ERROR,
            task_id=task_id,
            error="Page not found",
        )

        async def send_error():
            await asyncio.sleep(0.1)
            await manager.handle_message("test-ext-001", error_msg)

        task = asyncio.create_task(send_error())

        with pytest.raises(RuntimeError, match="Extension task failed"):
            await manager.wait_for_result(task_id, timeout=5)
        await task

    async def test_handle_progress(
        self,
        manager: ExtensionManager,
        mock_websocket: MagicMock,
        register_payload: RegisterPayload,
    ) -> None:
        """Progress messages should not raise errors."""
        manager.register(mock_websocket, register_payload)

        msg = WebSocketMessage.create(
            MessageType.PROGRESS,
            task_id="some-task",
            percent=50,
        )
        # Should not raise
        await manager.handle_message("test-ext-001", msg)

    async def test_handle_unknown_message(self, manager: ExtensionManager) -> None:
        """Unknown message types should be handled gracefully."""
        msg = WebSocketMessage(type=MessageType.REGISTERED, payload={})
        # Should not raise
        await manager.handle_message("ext-1", msg)


class TestDisconnectCleanup:
    """Tests for cleanup on disconnect."""

    async def test_unregister_fails_pending_tasks(
        self,
        manager: ExtensionManager,
        mock_websocket: MagicMock,
        register_payload: RegisterPayload,
    ) -> None:
        manager.register(mock_websocket, register_payload)

        task_id = await manager.dispatch_task(
            task_type=TaskType.SEARCH,
            params={"keyword": "test"},
        )

        # Grab the future before unregister cleans it up
        future = manager._pending_tasks[task_id]

        # Unregister should set exception on the future and remove it
        await manager.unregister("test-ext-001")

        assert future.done()
        with pytest.raises(ConnectionError):
            future.result()

    async def test_stop_fails_all_pending(
        self,
        manager: ExtensionManager,
        mock_websocket: MagicMock,
        register_payload: RegisterPayload,
    ) -> None:
        manager.register(mock_websocket, register_payload)

        task_id = await manager.dispatch_task(
            task_type=TaskType.PRODUCT,
            params={"shopId": 1, "itemId": 2},
        )

        await manager.stop()

        with pytest.raises(KeyError):
            await manager.wait_for_result(task_id, timeout=1)
