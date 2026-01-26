"""Base extractor class."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from shopee_scraper.utils.constants import (
    DEFAULT_MAX_RETRIES,
    LOGIN_URL_PATTERN,
    PAGE_LOAD_DELAY,
    POST_ACTION_DELAY,
    VERIFICATION_WAIT_DELAY,
    VERIFY_URL_PATTERN,
)
from shopee_scraper.utils.logging import get_logger
from shopee_scraper.utils.network_interceptor import NetworkInterceptor


if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from shopee_scraper.core.browser import BrowserManager, Page
    from shopee_scraper.utils.captcha_solver import CaptchaSolver

logger = get_logger(__name__)


class BaseExtractor(ABC):
    """Abstract base class for data extractors."""

    # Subclasses should set these in __init__
    browser: BrowserManager | None = None
    captcha_solver: CaptchaSolver | None = None

    @abstractmethod
    async def extract(self, page: Page) -> dict[str, Any]:
        """Extract data from page."""
        ...

    @abstractmethod
    def parse(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """Parse and clean extracted data."""
        ...

    async def navigate_with_retry(
        self, page: Page, url: str, max_retries: int = DEFAULT_MAX_RETRIES
    ) -> bool:
        """
        Navigate to URL with retry on traffic verification and captcha solving.

        Args:
            page: Browser page to navigate
            url: Target URL
            max_retries: Maximum number of retry attempts

        Returns:
            True if navigation successful, False if blocked by login/verification
        """
        if self.browser is None:
            raise RuntimeError("Browser not set on extractor")

        for attempt in range(max_retries):
            await self.browser.goto(page, url)

            current_url = page.target.url or ""

            # Login required - not recoverable
            if LOGIN_URL_PATTERN in current_url:
                return False

            # Not on verify page - success
            if VERIFY_URL_PATTERN not in current_url:
                return True

            # On verify page - try to solve captcha
            logger.warning(
                f"Traffic verification detected (attempt {attempt + 1}/{max_retries})",
                url=current_url,
            )

            # Try auto-solve captcha if solver is available
            if self.captcha_solver and self.captcha_solver.is_available:
                logger.info("Attempting to auto-solve CAPTCHA...")
                solved = await self.captcha_solver.solve_shopee_slider(page)
                if solved:
                    logger.info("CAPTCHA solved successfully")
                    await asyncio.sleep(POST_ACTION_DELAY)
                    current_url = page.target.url or ""
                    if VERIFY_URL_PATTERN not in current_url:
                        return True
                else:
                    logger.warning("CAPTCHA solving failed, waiting...")
            else:
                logger.info("No captcha solver available, waiting for manual solve...")

            await asyncio.sleep(VERIFICATION_WAIT_DELAY)

            current_url = page.target.url or ""
            if VERIFY_URL_PATTERN not in current_url:
                return True

        logger.error("Traffic verification persists after retries")
        return False

    # Backwards compatibility alias
    async def _navigate_with_retry(
        self, page: Page, url: str, max_retries: int = 3
    ) -> bool:
        """Alias for navigate_with_retry (backwards compatibility)."""
        return await self.navigate_with_retry(page, url, max_retries)

    async def handle_verify_redirect(
        self, page: Page, original_url: str, max_attempts: int = DEFAULT_MAX_RETRIES
    ) -> bool:
        """
        Handle verification redirect by solving captcha and navigating back.

        Args:
            page: Current page on verify URL
            original_url: URL to navigate back to after solving
            max_attempts: Maximum solve attempts

        Returns:
            True if verification resolved and back on original page
        """
        if self.browser is None:
            raise RuntimeError("Browser not set on extractor")

        for attempt in range(max_attempts):
            current_url = page.target.url or ""

            # Already resolved
            if VERIFY_URL_PATTERN not in current_url:
                return True

            logger.info(
                f"Handling verification redirect (attempt {attempt + 1}/{max_attempts})"
            )

            # Try auto-solve if available
            if self.captcha_solver and self.captcha_solver.is_available:
                logger.info("Attempting to auto-solve verification CAPTCHA...")
                solved = await self.captcha_solver.solve_shopee_slider(page)

                if solved:
                    logger.info("CAPTCHA solved, navigating back")
                    await asyncio.sleep(POST_ACTION_DELAY)

                    # Navigate back to original URL
                    await self.browser.goto(page, original_url)
                    await asyncio.sleep(POST_ACTION_DELAY)

                    current_url = page.target.url or ""
                    if VERIFY_URL_PATTERN not in current_url:
                        logger.info("Successfully returned to original page")
                        return True
                    else:
                        logger.warning("Still on verify page after solve attempt")
                else:
                    logger.warning("CAPTCHA solve failed")
            else:
                logger.warning("No captcha solver available")

            # Wait before retry
            await asyncio.sleep(PAGE_LOAD_DELAY)

        logger.error("Failed to resolve verification after all attempts")
        return False

    # Backwards compatibility alias
    async def _handle_verify_redirect(
        self, page: Page, original_url: str, max_attempts: int = 3
    ) -> bool:
        """Alias for handle_verify_redirect (backwards compatibility)."""
        return await self.handle_verify_redirect(page, original_url, max_attempts)

    @asynccontextmanager
    async def network_interception(
        self, page: Page, url_patterns: list[str] | None = None
    ) -> AsyncIterator[NetworkInterceptor]:
        """
        Context manager for network interception.

        Usage:
            async with self.network_interception(page, SEARCH_API_PATTERNS) as interceptor:
                await self.browser.goto(page, url)
                response = await interceptor.wait_for_response(SEARCH_API)

        Args:
            page: Browser page to intercept
            url_patterns: List of URL patterns to capture (uses defaults if None)

        Yields:
            NetworkInterceptor instance
        """
        interceptor = NetworkInterceptor(page)
        try:
            await interceptor.start(url_patterns)
            logger.debug("Network interception started", patterns=url_patterns)
            yield interceptor
        finally:
            await interceptor.stop()
            logger.debug("Network interception stopped")
