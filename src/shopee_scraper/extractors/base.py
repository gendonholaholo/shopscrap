"""Base extractor class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from shopee_scraper.core.browser import Page


class BaseExtractor(ABC):
    """Abstract base class for data extractors."""

    @abstractmethod
    async def extract(self, page: Page) -> dict[str, Any]:
        """Extract data from page."""
        ...

    @abstractmethod
    def parse(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """Parse and clean extracted data."""
        ...
