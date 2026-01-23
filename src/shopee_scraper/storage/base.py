"""Base storage interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseStorage(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    async def save(self, data: list[dict[str, Any]], filename: str) -> str:
        """Save data and return file path."""
        ...

    @abstractmethod
    async def load(self, filename: str) -> list[dict[str, Any]]:
        """Load data from storage."""
        ...
