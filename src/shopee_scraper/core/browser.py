"""Browser manager using nodriver for undetectable Chrome automation."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import nodriver
from nodriver.core.util import ProxyForwarder

from shopee_scraper.utils.logging import get_logger
from shopee_scraper.utils.proxy import ProxyConfig, ProxyPool


if TYPE_CHECKING:
    from nodriver import Tab as Page
else:
    Page = nodriver.Tab

# Export Page for other modules
__all__ = ["BrowserManager", "Page"]

logger = get_logger(__name__)


class BrowserManager:
    """
    Manages Chrome browser instances via nodriver for anti-detection.

    Features:
    - Undetectable browser automation (no WebDriver detection)
    - Proxy support with authentication via ProxyForwarder
    - Human-like behavior simulation
    - Session persistence via user data directory
    """

    def __init__(
        self,
        headless: bool = True,
        proxy: ProxyConfig | None = None,
        proxy_pool: ProxyPool | None = None,
        user_data_dir: str | None = None,
        timeout: int = 30000,
    ) -> None:
        self.headless = headless
        self.proxy = proxy
        self.proxy_pool = proxy_pool
        self.user_data_dir = user_data_dir
        self.timeout = timeout

        self._browser: nodriver.Browser | None = None
        self._pages: list[Page] = []
        self._current_proxy: ProxyConfig | None = None
        self._proxy_forwarder: ProxyForwarder | None = None

    async def _wait_for_proxy_ready(self, timeout: float = 10.0) -> bool:
        """Wait for ProxyForwarder server to be ready.

        Args:
            timeout: Maximum seconds to wait for proxy server.

        Returns:
            True if proxy server is ready, False if timeout or error.
        """
        if not self._proxy_forwarder:
            return False

        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < timeout:
            if self._proxy_forwarder.server is not None:
                # Verify server is actually serving by testing connection
                try:
                    _, writer = await asyncio.wait_for(
                        asyncio.open_connection(
                            self._proxy_forwarder.host,
                            self._proxy_forwarder.port,
                        ),
                        timeout=1.0,
                    )
                    writer.close()
                    await writer.wait_closed()
                    logger.debug(
                        "Proxy server connection test passed",
                        host=self._proxy_forwarder.host,
                        port=self._proxy_forwarder.port,
                    )
                    return True
                except Exception as e:
                    logger.debug("Proxy connection test failed, retrying", error=str(e))
            await asyncio.sleep(0.1)

        logger.error("Proxy forwarder failed to start within timeout", timeout=timeout)
        return False

    async def start(self) -> None:
        """Start Chrome browser via nodriver."""
        # Determine which proxy to use
        current_proxy = None
        if self.proxy:
            current_proxy = self.proxy
        elif self.proxy_pool and not self.proxy_pool.is_empty:
            current_proxy = self.proxy_pool.get_next()
            if current_proxy:
                logger.info("Using proxy from pool", host=current_proxy.host)

        self._current_proxy = current_proxy

        logger.info(
            "Starting Chrome browser",
            headless=self.headless,
            has_proxy=current_proxy is not None,
        )

        user_data = self.user_data_dir or "./data/chrome_profile"
        Path(user_data).mkdir(parents=True, exist_ok=True)

        # Build browser args
        browser_args = [
            "--no-first-run",
            "--no-default-browser-check",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ]

        # Setup proxy with authentication via ProxyForwarder
        if current_proxy:
            proxy_url = current_proxy.to_url()
            logger.info(
                "Setting up proxy forwarder",
                host=current_proxy.host,
                port=current_proxy.port,
            )

            # ProxyForwarder handles authenticated proxies by creating
            # a local proxy that forwards to the upstream with auth
            self._proxy_forwarder = ProxyForwarder(proxy_url)

            # Wait for forwarder server to be fully ready (fixes Docker race condition)
            if not await self._wait_for_proxy_ready(timeout=10.0):
                logger.error("Proxy forwarder failed to start")
                raise RuntimeError(
                    "Failed to initialize proxy forwarder within timeout"
                )

            # Use the local proxy URL (no auth needed for Chrome)
            local_proxy = self._proxy_forwarder.proxy_server
            browser_args.append(f"--proxy-server={local_proxy}")
            logger.info("Proxy forwarder ready", local_proxy=local_proxy)

        self._browser = await nodriver.start(
            headless=self.headless,
            user_data_dir=user_data,
            browser_args=browser_args,
            lang="id-ID",
        )

        logger.info("Browser started successfully")

    async def new_page(self) -> Page:
        """Create a new tab in the browser."""
        if not self._browser:
            await self.start()

        tab = await self._browser.get("about:blank", new_tab=True)  # type: ignore
        self._pages.append(tab)
        logger.debug("New page created", total_pages=len(self._pages))
        return tab

    async def goto(
        self,
        page: Page,
        url: str,
        wait_until: str = "domcontentloaded",
    ) -> None:
        """Navigate to URL with human-like behavior."""
        logger.info("Navigating to URL", url=url)

        try:
            await page.get(url)
            # Wait for page to settle
            await self.random_delay(1.0, 2.5)
        except Exception as e:
            logger.error("Navigation failed", url=url, error=str(e))
            raise

    async def random_delay(self, min_sec: float = 0.5, max_sec: float = 2.0) -> None:
        """Add random delay to simulate human behavior."""
        import random

        delay = random.uniform(min_sec, max_sec)
        await asyncio.sleep(delay)

    async def scroll_page(self, page: Page, scroll_count: int = 3) -> None:
        """Scroll page to load dynamic content."""
        for i in range(scroll_count):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await self.random_delay(0.5, 1.5)
            logger.debug("Page scrolled", scroll=i + 1, total=scroll_count)

    async def wait_for_selector_safe(
        self,
        page: Page,
        selector: str,
        timeout: int | None = None,
    ) -> bool:
        """Wait for selector with error handling."""
        effective_timeout = (timeout or self.timeout) / 1000  # ms to seconds
        try:
            element = await page.find(selector, timeout=effective_timeout)
            if element is None:
                logger.warning("Selector not found", selector=selector)
                return False
            return True
        except Exception:
            logger.warning("Selector not found", selector=selector)
            return False

    async def get_cookies(self) -> list[dict[str, Any]]:
        """Get all cookies from browser."""
        if not self._browser:
            return []

        import nodriver.cdp.network as net

        tab = self._browser.main_tab
        result = await tab.send(net.get_all_cookies())
        cookies = []
        for c in result:
            cookies.append(
                {
                    "name": c.name,
                    "value": c.value,
                    "domain": c.domain,
                    "path": c.path,
                    "expires": c.expires,
                    "httpOnly": c.http_only,
                    "secure": c.secure,
                    "sameSite": c.same_site.value if c.same_site else "Lax",
                }
            )
        return cookies

    async def set_cookies(self, cookies: list[dict[str, Any]]) -> None:
        """Set cookies in browser."""
        if not self._browser or not cookies:
            return

        import nodriver.cdp.network as net

        cookie_params = []
        for c in cookies:
            cookie_params.append(
                net.CookieParam(
                    name=c["name"],
                    value=c["value"],
                    domain=c.get("domain", ".shopee.co.id"),
                    path=c.get("path", "/"),
                )
            )

        tab = self._browser.main_tab
        await tab.send(net.set_cookies(cookie_params))
        logger.info("Cookies set", count=len(cookies))

    async def close_page(self, page: Page) -> None:
        """Close a specific tab."""
        if page in self._pages:
            self._pages.remove(page)
        with contextlib.suppress(Exception):
            await page.close()
        logger.debug("Page closed", remaining_pages=len(self._pages))

    async def close(self) -> None:
        """Close browser and cleanup."""
        logger.info("Closing browser")

        for page in self._pages:
            with contextlib.suppress(Exception):
                await page.close()
        self._pages.clear()

        if self._browser:
            with contextlib.suppress(Exception):
                self._browser.stop()
            self._browser = None

        # Cleanup proxy forwarder with timeout
        if self._proxy_forwarder and self._proxy_forwarder.server:
            try:
                self._proxy_forwarder.server.close()
                await asyncio.wait_for(
                    self._proxy_forwarder.server.wait_closed(),
                    timeout=5.0,
                )
                logger.debug("Proxy forwarder closed successfully")
            except asyncio.TimeoutError:
                logger.warning("Proxy forwarder cleanup timeout")
            except Exception as e:
                logger.warning("Proxy forwarder cleanup error", error=str(e))
        self._proxy_forwarder = None

        logger.info("Browser closed")

    async def rotate_proxy(self) -> bool:
        """Rotate to next proxy in pool."""
        if not self.proxy_pool or self.proxy_pool.is_empty:
            logger.warning("No proxy pool available for rotation")
            return False

        await self.close()
        self.proxy = self.proxy_pool.get_next()
        if self.proxy:
            logger.info("Rotated to new proxy", host=self.proxy.host)
        await self.start()
        return True

    @property
    def current_proxy(self) -> ProxyConfig | None:
        """Get the currently active proxy configuration."""
        return self._current_proxy

    async def __aenter__(self) -> BrowserManager:
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        """Async context manager exit."""
        await self.close()
