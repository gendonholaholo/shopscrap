"""Unit tests for BrowserManager."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shopee_scraper.core.browser import BrowserManager


class TestBrowserManagerInit:
    """Tests for BrowserManager initialization."""

    def test_init_default_headless_true(self) -> None:
        """Default headless mode is True."""
        manager = BrowserManager()

        assert manager.headless is True

    def test_init_headless_false(self) -> None:
        """Headless can be set to False."""
        manager = BrowserManager(headless=False)

        assert manager.headless is False

    def test_init_default_timeout(self) -> None:
        """Default timeout is 30000ms."""
        manager = BrowserManager()

        assert manager.timeout == 30000

    def test_init_custom_timeout(self) -> None:
        """Custom timeout can be set."""
        manager = BrowserManager(timeout=60000)

        assert manager.timeout == 60000

    def test_init_no_browser_started(self) -> None:
        """Browser is not started on init."""
        manager = BrowserManager()

        assert manager._browser is None
        assert manager._pages == []

    def test_init_proxy_config(self) -> None:
        """Proxy config can be provided."""
        from shopee_scraper.utils.proxy import ProxyConfig

        proxy = ProxyConfig(host="proxy.example.com", port=8080)
        manager = BrowserManager(proxy=proxy)

        assert manager.proxy == proxy

    def test_init_user_data_dir(self) -> None:
        """User data directory can be set."""
        manager = BrowserManager(user_data_dir="/custom/path")

        assert manager.user_data_dir == "/custom/path"


class TestRandomDelay:
    """Tests for random delay functionality."""

    @pytest.mark.asyncio
    async def test_random_delay_within_range(self) -> None:
        """Delay is within specified range."""
        manager = BrowserManager()

        start = asyncio.get_event_loop().time()
        await manager.random_delay(0.1, 0.2)
        elapsed = asyncio.get_event_loop().time() - start

        # Allow some tolerance for timing
        assert 0.09 <= elapsed <= 0.3

    @pytest.mark.asyncio
    async def test_random_delay_default_range(self) -> None:
        """Default delay range is 0.5-2.0 seconds."""
        manager = BrowserManager()

        # Just verify it doesn't error with defaults
        # Don't actually wait the full time
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await manager.random_delay()

            # Check sleep was called with value in range
            call_args = mock_sleep.call_args[0][0]
            assert 0.5 <= call_args <= 2.0


class TestPageManagement:
    """Tests for page/tab management."""

    @pytest.mark.asyncio
    async def test_new_page_starts_browser_if_needed(self) -> None:
        """new_page starts browser if not already started."""
        manager = BrowserManager()
        manager.start = AsyncMock()

        # Mock browser after start
        mock_browser = MagicMock()
        mock_tab = MagicMock()
        mock_browser.get = AsyncMock(return_value=mock_tab)

        async def fake_start() -> None:
            manager._browser = mock_browser

        manager.start = fake_start

        page = await manager.new_page()

        assert page == mock_tab
        assert mock_tab in manager._pages

    @pytest.mark.asyncio
    async def test_close_page_removes_from_list(self) -> None:
        """Closing page removes it from tracked pages."""
        manager = BrowserManager()
        mock_page = MagicMock()
        mock_page.close = AsyncMock()
        manager._pages = [mock_page]

        await manager.close_page(mock_page)

        assert mock_page not in manager._pages
        mock_page.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_page_handles_error(self) -> None:
        """Closing page handles errors gracefully."""
        manager = BrowserManager()
        mock_page = MagicMock()
        mock_page.close = AsyncMock(side_effect=Exception("Close failed"))
        manager._pages = [mock_page]

        # Should not raise
        await manager.close_page(mock_page)

        assert mock_page not in manager._pages


class TestBrowserLifecycle:
    """Tests for browser start/close lifecycle."""

    @pytest.mark.asyncio
    async def test_close_clears_pages(self) -> None:
        """Close clears all tracked pages."""
        manager = BrowserManager()
        mock_page1 = MagicMock()
        mock_page1.close = AsyncMock()
        mock_page2 = MagicMock()
        mock_page2.close = AsyncMock()
        manager._pages = [mock_page1, mock_page2]
        manager._browser = MagicMock()
        manager._browser.stop = MagicMock()

        await manager.close()

        assert manager._pages == []
        assert manager._browser is None

    @pytest.mark.asyncio
    async def test_context_manager_starts_and_closes(self) -> None:
        """Context manager calls start and close."""
        manager = BrowserManager()
        manager.start = AsyncMock()
        manager.close = AsyncMock()

        async with manager:
            manager.start.assert_called_once()

        manager.close.assert_called_once()


class TestCookieOperations:
    """Tests for cookie get/set operations."""

    @pytest.mark.asyncio
    async def test_get_cookies_no_browser_returns_empty(self) -> None:
        """get_cookies returns empty list if browser not started."""
        manager = BrowserManager()
        manager._browser = None

        cookies = await manager.get_cookies()

        assert cookies == []

    @pytest.mark.asyncio
    async def test_set_cookies_no_browser_does_nothing(self) -> None:
        """set_cookies does nothing if browser not started."""
        manager = BrowserManager()
        manager._browser = None

        # Should not raise
        await manager.set_cookies([{"name": "test", "value": "123"}])

    @pytest.mark.asyncio
    async def test_set_cookies_empty_list_does_nothing(self) -> None:
        """set_cookies does nothing with empty cookie list."""
        manager = BrowserManager()
        manager._browser = MagicMock()

        # Should not raise or make any calls
        await manager.set_cookies([])


class TestProxyRotation:
    """Tests for proxy rotation functionality."""

    @pytest.mark.asyncio
    async def test_rotate_proxy_no_pool_returns_false(self) -> None:
        """rotate_proxy returns False when no proxy pool."""
        manager = BrowserManager()
        manager.proxy_pool = None

        result = await manager.rotate_proxy()

        assert result is False

    @pytest.mark.asyncio
    async def test_rotate_proxy_empty_pool_returns_false(self) -> None:
        """rotate_proxy returns False when pool is empty."""
        manager = BrowserManager()

        mock_pool = MagicMock()
        mock_pool.is_empty = True
        manager.proxy_pool = mock_pool

        result = await manager.rotate_proxy()

        assert result is False


class TestScrollPage:
    """Tests for page scrolling functionality."""

    @pytest.mark.asyncio
    async def test_scroll_page_evaluates_js(self) -> None:
        """scroll_page executes JavaScript scroll commands."""
        manager = BrowserManager()
        mock_page = MagicMock()
        mock_page.evaluate = AsyncMock()

        with patch.object(manager, "random_delay", new_callable=AsyncMock):
            await manager.scroll_page(mock_page, scroll_count=3)

        assert mock_page.evaluate.call_count == 3

    @pytest.mark.asyncio
    async def test_scroll_page_default_count(self) -> None:
        """Default scroll count is 3."""
        manager = BrowserManager()
        mock_page = MagicMock()
        mock_page.evaluate = AsyncMock()

        with patch.object(manager, "random_delay", new_callable=AsyncMock):
            await manager.scroll_page(mock_page)

        assert mock_page.evaluate.call_count == 3


class TestWaitForSelector:
    """Tests for wait_for_selector_safe functionality."""

    @pytest.mark.asyncio
    async def test_wait_for_selector_found(self) -> None:
        """Returns True when element is found."""
        manager = BrowserManager()
        mock_page = MagicMock()
        mock_element = MagicMock()
        mock_page.find = AsyncMock(return_value=mock_element)

        result = await manager.wait_for_selector_safe(mock_page, "input[name='test']")

        assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_selector_not_found(self) -> None:
        """Returns False when element is not found."""
        manager = BrowserManager()
        mock_page = MagicMock()
        mock_page.find = AsyncMock(return_value=None)

        result = await manager.wait_for_selector_safe(mock_page, "input[name='test']")

        assert result is False

    @pytest.mark.asyncio
    async def test_wait_for_selector_exception(self) -> None:
        """Returns False when exception occurs."""
        manager = BrowserManager()
        mock_page = MagicMock()
        mock_page.find = AsyncMock(side_effect=Exception("Timeout"))

        result = await manager.wait_for_selector_safe(mock_page, "input[name='test']")

        assert result is False

    @pytest.mark.asyncio
    async def test_wait_for_selector_custom_timeout(self) -> None:
        """Custom timeout is converted from ms to seconds."""
        manager = BrowserManager(timeout=30000)
        mock_page = MagicMock()
        mock_page.find = AsyncMock(return_value=MagicMock())

        await manager.wait_for_selector_safe(
            mock_page, "input[name='test']", timeout=5000
        )

        # 5000ms should become 5 seconds
        mock_page.find.assert_called_once_with("input[name='test']", timeout=5.0)
