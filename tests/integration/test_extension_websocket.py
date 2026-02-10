"""Integration tests for extension WebSocket endpoint."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from shopee_scraper.extension.manager import ExtensionManager, init_extension_manager


@pytest.fixture
async def extension_manager() -> ExtensionManager:
    """Initialize a test ExtensionManager."""
    manager = await init_extension_manager(task_timeout=5, heartbeat_timeout=60)
    yield manager
    await manager.stop()


@pytest.mark.integration
class TestExtensionWebSocket:
    """Integration tests for the extension WebSocket flow."""

    def test_websocket_register_flow(self, extension_manager: ExtensionManager) -> None:
        """Test WebSocket connect → register → registered response."""
        from shopee_scraper.api.main import create_app

        app = create_app()
        client = TestClient(app)

        with client.websocket_connect("/api/v1/extension/connect") as ws:
            # Send registration
            register_msg = {
                "type": "register",
                "payload": {
                    "extension_id": "test-ws-ext-001",
                    "user_agent": "TestClient/1.0",
                    "version": "1.0",
                },
            }
            ws.send_text(json.dumps(register_msg))

            # Should receive registered response
            response = json.loads(ws.receive_text())
            assert response["type"] == "registered"
            assert response["payload"]["status"] == "ok"

    def test_websocket_heartbeat(self, extension_manager: ExtensionManager) -> None:
        """Test heartbeat → pong flow."""
        from shopee_scraper.api.main import create_app

        app = create_app()
        client = TestClient(app)

        with client.websocket_connect("/api/v1/extension/connect") as ws:
            # Register first
            ws.send_text(
                json.dumps(
                    {
                        "type": "register",
                        "payload": {
                            "extension_id": "test-ws-ext-002",
                            "user_agent": "TestClient/1.0",
                            "version": "1.0",
                        },
                    }
                )
            )
            # Consume registered response
            ws.receive_text()

            # Send heartbeat
            ws.send_text(
                json.dumps(
                    {
                        "type": "heartbeat",
                        "payload": {"extension_id": "test-ws-ext-002"},
                    }
                )
            )

            # Should receive pong
            response = json.loads(ws.receive_text())
            assert response["type"] == "pong"

    def test_websocket_invalid_first_message(
        self, extension_manager: ExtensionManager
    ) -> None:
        """Test that non-register first message gets rejected."""
        from shopee_scraper.api.main import create_app

        app = create_app()
        client = TestClient(app)

        with client.websocket_connect("/api/v1/extension/connect") as ws:
            # Send heartbeat as first message (should be register)
            ws.send_text(
                json.dumps(
                    {
                        "type": "heartbeat",
                        "payload": {},
                    }
                )
            )

            # Should receive error
            response = json.loads(ws.receive_text())
            assert "error" in response
