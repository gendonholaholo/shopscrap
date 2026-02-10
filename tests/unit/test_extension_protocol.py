"""Unit tests for extension protocol module."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from shopee_scraper.extension.protocol import (
    MessageType,
    ProgressPayload,
    RegisteredResponse,
    RegisterPayload,
    TaskAssignment,
    TaskErrorPayload,
    TaskResultPayload,
    TaskType,
    WebSocketMessage,
)


class TestMessageType:
    """Tests for MessageType enum."""

    def test_extension_to_backend_types(self) -> None:
        assert MessageType.REGISTER == "register"
        assert MessageType.HEARTBEAT == "heartbeat"
        assert MessageType.TASK_RESULT == "task_result"
        assert MessageType.TASK_ERROR == "task_error"
        assert MessageType.PROGRESS == "progress"

    def test_backend_to_extension_types(self) -> None:
        assert MessageType.REGISTERED == "registered"
        assert MessageType.PONG == "pong"
        assert MessageType.TASK == "task"
        assert MessageType.CANCEL_TASK == "cancel_task"


class TestTaskType:
    """Tests for TaskType enum."""

    def test_task_types(self) -> None:
        assert TaskType.SEARCH == "search"
        assert TaskType.PRODUCT == "product"
        assert TaskType.REVIEWS == "reviews"


class TestPayloadModels:
    """Tests for Pydantic payload models."""

    def test_register_payload(self) -> None:
        payload = RegisterPayload(
            extension_id="test-ext-123",
            user_agent="Mozilla/5.0",
            version="1.0",
        )
        assert payload.extension_id == "test-ext-123"
        assert payload.user_agent == "Mozilla/5.0"

    def test_register_payload_defaults(self) -> None:
        payload = RegisterPayload(extension_id="abc")
        assert payload.user_agent == ""
        assert payload.version == "1.0"

    def test_task_result_payload(self) -> None:
        payload = TaskResultPayload(
            task_id="task-1",
            raw_data={"items": [{"name": "test"}]},
        )
        assert payload.task_id == "task-1"
        assert payload.raw_data["items"][0]["name"] == "test"

    def test_task_error_payload(self) -> None:
        payload = TaskErrorPayload(
            task_id="task-2",
            error="Connection timeout",
            details="Failed to load page",
        )
        assert payload.error == "Connection timeout"
        assert payload.details == "Failed to load page"

    def test_task_error_payload_no_details(self) -> None:
        payload = TaskErrorPayload(task_id="task-3", error="Error")
        assert payload.details is None

    def test_progress_payload(self) -> None:
        payload = ProgressPayload(task_id="task-1", percent=50, message="Loading")
        assert payload.percent == 50
        assert payload.message == "Loading"

    def test_progress_payload_validation(self) -> None:
        """Progress percent must be 0-100."""
        with pytest.raises(ValidationError):
            ProgressPayload(task_id="t", percent=150)

        with pytest.raises(ValidationError):
            ProgressPayload(task_id="t", percent=-1)

    def test_registered_response(self) -> None:
        resp = RegisteredResponse()
        assert resp.status == "ok"
        assert resp.server_version == "1.0"

    def test_task_assignment(self) -> None:
        task = TaskAssignment(
            task_id="task-5",
            task_type=TaskType.SEARCH,
            params={"keyword": "laptop", "maxPages": 2},
        )
        assert task.task_id == "task-5"
        assert task.task_type == TaskType.SEARCH
        assert task.params["keyword"] == "laptop"


class TestWebSocketMessage:
    """Tests for WebSocketMessage envelope."""

    def test_create_message(self) -> None:
        msg = WebSocketMessage.create(
            MessageType.REGISTER,
            extension_id="ext-1",
            user_agent="Chrome",
        )
        assert msg.type == MessageType.REGISTER
        assert msg.payload["extension_id"] == "ext-1"
        assert msg.payload["user_agent"] == "Chrome"

    def test_to_json_str(self) -> None:
        msg = WebSocketMessage.create(MessageType.HEARTBEAT, extension_id="ext-1")
        json_str = msg.to_json_str()
        parsed = json.loads(json_str)
        assert parsed["type"] == "heartbeat"
        assert parsed["payload"]["extension_id"] == "ext-1"

    def test_roundtrip_serialization(self) -> None:
        msg = WebSocketMessage.create(
            MessageType.TASK_RESULT,
            task_id="t-1",
            raw_data={"items": []},
        )
        json_str = msg.to_json_str()
        restored = WebSocketMessage.model_validate_json(json_str)
        assert restored.type == MessageType.TASK_RESULT
        assert restored.payload["task_id"] == "t-1"

    def test_empty_payload(self) -> None:
        msg = WebSocketMessage.create(MessageType.PONG)
        assert msg.payload == {}
        json_str = msg.to_json_str()
        parsed = json.loads(json_str)
        assert parsed["payload"] == {}
