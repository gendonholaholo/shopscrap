"""Chrome Extension backend module for Shopee Scraper."""

from shopee_scraper.extension.protocol import (
    MessageType,
    TaskType,
    WebSocketMessage,
)


__all__ = [
    "MessageType",
    "TaskType",
    "WebSocketMessage",
]
