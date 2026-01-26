"""Browser manager using nodriver for undetectable Chrome automation."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import nodriver

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
    - Proxy support
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

    async def start(self) -> None:
        """Start Chrome browser via nodriver."""
        logger.info(
            "Starting Chrome browser",
            headless=self.headless,
            has_proxy=self.proxy is not None
            or (self.proxy_pool and not self.proxy_pool.is_empty),
        )

        user_data = self.user_data_dir or "./data/chrome_profile"
        Path(user_data).mkdir(parents=True, exist_ok=True)

        # Build browser args (nodriver handles --headless via its parameter)
        browser_args = [
            "--no-first-run",
            "--no-default-browser-check",
            # Required for Docker/containerized environments
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ]

        # Get proxy configuration
        current_proxy = None
        if self.proxy:
            current_proxy = self.proxy
        elif self.proxy_pool and not self.proxy_pool.is_empty:
            current_proxy = self.proxy_pool.get_next()
            if current_proxy:
                logger.info("Using proxy from pool", host=current_proxy.host)

        # For authenticated proxies, we use --proxy-server without credentials
        # and handle authentication via CDP Fetch.authRequired
        if current_proxy:
            # Use proxy server without credentials in URL
            proxy_server = (
                f"{current_proxy.protocol}://{current_proxy.host}:{current_proxy.port}"
            )
            browser_args.append(f"--proxy-server={proxy_server}")
            self._current_proxy = current_proxy
        else:
            self._current_proxy = None

        self._browser = await nodriver.start(
            headless=self.headless,
            user_data_dir=user_data,
            browser_args=browser_args,
            lang="id-ID",
        )

        # Setup proxy authentication handler if we have credentials
        if current_proxy and current_proxy.username and current_proxy.password:
            await self._setup_proxy_auth(current_proxy)

        logger.info("Browser started successfully")

    async def _setup_proxy_auth(self, proxy: ProxyConfig) -> None:
        """Setup proxy authentication using CDP Fetch domain."""
        from nodriver.cdp import fetch

        if self._browser is None:
            return

        tab = self._browser.main_tab

        # Enable Fetch with auth required handling
        await tab.send(fetch.enable(handle_auth_requests=True))

        # Add handler for auth challenges
        async def handle_auth_required(event: fetch.AuthRequired) -> None:
            """Handle 407 Proxy Authentication Required."""
            logger.debug(
                "Proxy auth required",
                request_id=event.request_id,
                host=proxy.host,
            )
            await tab.send(
                fetch.continue_with_auth(
                    request_id=event.request_id,
                    auth_challenge_response=fetch.AuthChallengeResponse(
                        response="ProvideCredentials",
                        username=proxy.username,
                        password=proxy.password,
                    ),
                )
            )

        # Add handler for continuing requests after auth
        async def handle_request_paused(event: fetch.RequestPaused) -> None:
            """Continue paused requests."""
            await tab.send(fetch.continue_request(request_id=event.request_id))

        tab.add_handler(fetch.AuthRequired, handle_auth_required)
        tab.add_handler(fetch.RequestPaused, handle_request_paused)

        logger.info("Proxy authentication handler configured")

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

    async def __aenter__(self) -> BrowserManager:
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        """Async context manager exit."""
        await self.close()
