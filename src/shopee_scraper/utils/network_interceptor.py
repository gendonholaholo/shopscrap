"""Network interceptor for capturing API responses via CDP.

This module provides network interception capabilities using Chrome DevTools Protocol.
It captures Shopee's internal API responses (JSON) instead of relying on DOM selectors,
which are much more stable as API response structures change less frequently.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import nodriver.cdp.network as net

from shopee_scraper.utils.constants import ALL_API_PATTERNS
from shopee_scraper.utils.logging import get_logger


if TYPE_CHECKING:
    from collections.abc import Callable

    from nodriver import Tab

logger = get_logger(__name__)


@dataclass
class InterceptedResponse:
    """Represents an intercepted network response."""

    url: str
    status: int
    headers: dict[str, str]
    body: str | None = None
    body_json: dict[str, Any] | None = None
    request_id: str = ""


@dataclass
class NetworkInterceptor:
    """
    Intercepts network responses using Chrome DevTools Protocol.

    This allows capturing Shopee's internal API responses directly,
    bypassing the need for DOM selectors which change frequently.

    Usage:
        interceptor = NetworkInterceptor(tab)
        await interceptor.start()

        # Navigate to page
        await tab.get(url)

        # Wait for and get specific API response
        response = await interceptor.wait_for_response("/api/v4/search/search_items")

        await interceptor.stop()
    """

    tab: Tab
    url_patterns: list[str] = field(default_factory=list)
    _responses: dict[str, InterceptedResponse] = field(default_factory=dict)
    _pending_requests: dict[str, str] = field(default_factory=dict)  # request_id -> url
    _enabled: bool = False
    _event_handlers: list[Callable] = field(default_factory=list)

    async def start(self, url_patterns: list[str] | None = None) -> None:
        """
        Start intercepting network responses.

        Args:
            url_patterns: List of URL substrings to capture (e.g., ["/api/v4/"])
                         If None, captures all responses
        """
        if self._enabled:
            return

        if url_patterns:
            self.url_patterns = url_patterns
        else:
            # Default Shopee API patterns from constants
            self.url_patterns = list(ALL_API_PATTERNS)

        # Enable network monitoring
        await self.tab.send(net.enable())

        # Register event handlers
        self.tab.add_handler(net.ResponseReceived, self._on_response_received)
        self.tab.add_handler(net.LoadingFinished, self._on_loading_finished)

        self._enabled = True
        logger.debug("Network interceptor started", patterns=self.url_patterns)

    async def stop(self) -> None:
        """Stop intercepting and cleanup."""
        if not self._enabled:
            return

        with contextlib.suppress(Exception):
            await self.tab.send(net.disable())

        self._enabled = False
        self._responses.clear()
        self._pending_requests.clear()
        logger.debug("Network interceptor stopped")

    async def _on_response_received(self, event: net.ResponseReceived) -> None:
        """Handle response received event."""
        url = event.response.url
        request_id = event.request_id

        # Check if URL matches our patterns
        if not self._should_capture(url):
            return

        # Store pending request for body retrieval
        self._pending_requests[request_id] = url

        # Check if we already have a valid response with data for this URL
        # Don't overwrite a good response with potentially error response from retry
        existing = self._responses.get(url)
        if existing and existing.body_json:
            # Check if existing response has actual product data
            has_items = (
                "items" in existing.body_json
                or ("data" in existing.body_json and "items" in existing.body_json.get("data", {}))
            )
            if has_items:
                logger.debug(
                    "Keeping existing valid response, skipping new capture",
                    url=url[:60],
                )
                return

        # Create response object
        headers = {}
        if event.response.headers:
            headers = dict(event.response.headers)

        self._responses[url] = InterceptedResponse(
            url=url,
            status=event.response.status,
            headers=headers,
            request_id=request_id,
        )

        logger.debug(
            "Response captured",
            url=url[:80],
            status=event.response.status,
        )

    async def _on_loading_finished(self, event: net.LoadingFinished) -> None:
        """Handle loading finished - retrieve response body."""
        request_id = event.request_id

        if request_id not in self._pending_requests:
            return

        url = self._pending_requests.pop(request_id)

        try:
            # Get response body via CDP
            result = await self.tab.send(net.get_response_body(request_id))
            body = result[0]  # response body string

            if url in self._responses:
                self._responses[url].body = body

                # Try to parse as JSON
                try:
                    self._responses[url].body_json = json.loads(body)
                    logger.debug("JSON response parsed", url=url[:60])
                except json.JSONDecodeError:
                    pass

        except Exception as e:
            logger.warning(f"Failed to get response body: {e}", url=url[:60])

    def _should_capture(self, url: str) -> bool:
        """Check if URL should be captured based on patterns."""
        if not self.url_patterns:
            return True
        return any(pattern in url for pattern in self.url_patterns)

    async def wait_for_response(
        self,
        url_pattern: str,
        timeout: float = 30.0,
        poll_interval: float = 0.5,
    ) -> InterceptedResponse | None:
        """
        Wait for a specific response matching the URL pattern.

        Args:
            url_pattern: Substring to match in URL
            timeout: Maximum wait time in seconds
            poll_interval: How often to check for response

        Returns:
            InterceptedResponse if found, None if timeout
        """
        elapsed = 0.0

        while elapsed < timeout:
            # Check for matching response with body
            for url, response in self._responses.items():
                if url_pattern in url and response.body is not None:
                    logger.debug(
                        "Response found",
                        pattern=url_pattern,
                        url=url[:60],
                    )
                    return response

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        logger.warning(f"Response timeout for pattern: {url_pattern}")
        return None

    def get_response(self, url_pattern: str) -> InterceptedResponse | None:
        """
        Get a captured response matching the URL pattern (non-blocking).

        Args:
            url_pattern: Substring to match in URL

        Returns:
            InterceptedResponse if found, None otherwise
        """
        for url, response in self._responses.items():
            if url_pattern in url:
                return response
        return None

    def get_all_responses(self) -> list[InterceptedResponse]:
        """Get all captured responses."""
        return list(self._responses.values())

    def clear_responses(self) -> None:
        """Clear all captured responses."""
        self._responses.clear()
