"""Message protocol and schemas for Chrome Extension communication."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# =============================================================================
# Protocol Constants
# =============================================================================

HEARTBEAT_INTERVAL_SECONDS = 30
HEARTBEAT_TIMEOUT_SECONDS = 90  # 3x interval = dead
TASK_TIMEOUT_SECONDS = 300
PROTOCOL_VERSION = "1.0"


# =============================================================================
# Message Types
# =============================================================================


class MessageType(str, Enum):
    """WebSocket message types for extension protocol."""

    # Extension → Backend
    REGISTER = "register"
    HEARTBEAT = "heartbeat"
    TASK_RESULT = "task_result"
    TASK_ERROR = "task_error"
    PROGRESS = "progress"

    # Backend → Extension
    REGISTERED = "registered"
    PONG = "pong"
    TASK = "task"
    CANCEL_TASK = "cancel_task"


class TaskType(str, Enum):
    """Types of scraping tasks dispatched to the extension."""

    SEARCH = "search"
    PRODUCT = "product"
    REVIEWS = "reviews"


# =============================================================================
# Extension → Backend Payloads
# =============================================================================


class RegisterPayload(BaseModel):
    """Sent by extension on connect to identify itself."""

    extension_id: str = Field(..., description="Unique extension instance ID")
    user_agent: str = Field(default="", description="Browser user agent string")
    version: str = Field(default="1.0", description="Extension version")


class HeartbeatPayload(BaseModel):
    """Periodic heartbeat from extension."""

    extension_id: str


class TaskResultPayload(BaseModel):
    """Result of a completed task from extension."""

    task_id: str = Field(..., description="Task ID assigned by backend")
    raw_data: dict[str, Any] = Field(..., description="Raw Shopee API JSON response")


class TaskErrorPayload(BaseModel):
    """Error report when a task fails."""

    task_id: str
    error: str = Field(..., description="Error message")
    details: str | None = Field(default=None, description="Additional error context")


class ProgressPayload(BaseModel):
    """Progress update for a running task."""

    task_id: str
    percent: int = Field(ge=0, le=100)
    message: str = Field(default="")


# =============================================================================
# Backend → Extension Payloads
# =============================================================================


class RegisteredResponse(BaseModel):
    """Confirmation sent to extension after successful registration."""

    status: str = "ok"
    server_version: str = PROTOCOL_VERSION


class TaskAssignment(BaseModel):
    """Task dispatched to extension for execution."""

    task_id: str = Field(..., description="Unique task ID")
    task_type: TaskType = Field(..., description="Type of scraping task")
    params: dict[str, Any] = Field(default_factory=dict, description="Task parameters")


class CancelTaskMessage(BaseModel):
    """Request to cancel a running task."""

    task_id: str


class PongMessage(BaseModel):
    """Heartbeat response."""

    pass


# =============================================================================
# Envelope: All messages are wrapped in this
# =============================================================================


class WebSocketMessage(BaseModel):
    """Top-level WebSocket message envelope."""

    type: MessageType
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_json_str(self) -> str:
        """Serialize to JSON string for sending over WebSocket."""
        return self.model_dump_json()

    @classmethod
    def create(cls, msg_type: MessageType, **payload_fields: Any) -> WebSocketMessage:
        """Create a message with the given type and payload fields."""
        return cls(type=msg_type, payload=payload_fields)
