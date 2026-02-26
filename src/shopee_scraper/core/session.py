"""Session management for persistent login state."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from shopee_scraper.utils.constants import BASE_URL, LOGIN_URL
from shopee_scraper.utils.logging import get_logger


if TYPE_CHECKING:
    from shopee_scraper.core.browser import BrowserManager, Page
    from shopee_scraper.utils.captcha_solver import CaptchaSolver

logger = get_logger(__name__)


class SessionManager:
    """
    Manages browser sessions, cookies, and authentication.

    Features:
    - Cookie persistence (save/load)
    - Login flow with credentials
    - Session validation
    - Auto-refresh expired sessions
    """

    # URLs imported from constants
    HOME_URL = BASE_URL

    # Selectors for login page (multiple alternatives for resilience)
    SELECTORS = {
        "username_input": "input[name='loginKey']",
        "password_input": "input[name='password']",
        "login_button": "form button[type='button']",
        "user_menu": "[class*='navbar__username']",
        "captcha": "[class*='captcha']",
        "otp_input": "input[name='otp']",
    }

    # Alternative selectors if primary ones fail
    ALT_SELECTORS = {
        "username_input": [
            "input[name='loginKey']",
            "input[type='text'][autocomplete='username']",
            "input[placeholder*='email']",
            "input[placeholder*='phone']",
            "input[placeholder*='Email']",
            "input[placeholder*='Nomor']",
            "[class*='login'] input[type='text']",
        ],
        "password_input": [
            "input[name='password']",
            "input[type='password']",
            "[class*='login'] input[type='password']",
        ],
    }

    def __init__(
        self,
        session_dir: str = "./data/sessions",
        captcha_solver: CaptchaSolver | None = None,
        use_anticaptcha: bool = False,
    ) -> None:
        """
        Initialize session manager.

        Args:
            session_dir: Directory to store session files
            captcha_solver: Optional CaptchaSolver instance for auto-solving
            use_anticaptcha: Whether to use anti-captcha service
        """
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._is_logged_in = False
        self.captcha_solver = captcha_solver
        self.use_anticaptcha = use_anticaptcha

    # =========================================================================
    # Cookie Management
    # =========================================================================

    def save_cookies(
        self,
        cookies: list[dict[str, Any]],
        name: str = "default",
    ) -> Path:
        """
        Save cookies to file.

        Args:
            cookies: List of cookie dictionaries
            name: Session name for the file
        """
        path = self.session_dir / f"{name}_cookies.json"
        data = {
            "cookies": cookies,
            "saved_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=7)).isoformat(),
        }
        with path.open("w") as f:
            json.dump(data, f, indent=2)
        logger.info("Cookies saved", path=str(path), count=len(cookies))
        return path

    def load_cookies(self, name: str = "default") -> list[dict[str, Any]] | None:
        """
        Load cookies from file.

        Args:
            name: Session name

        Returns:
            List of cookies or None if not found/expired
        """
        path = self.session_dir / f"{name}_cookies.json"
        if not path.exists():
            logger.debug("Cookie file not found", path=str(path))
            return None

        with path.open() as f:
            data = json.load(f)

        # Check expiration
        expires_at = datetime.fromisoformat(data.get("expires_at", "2000-01-01"))
        if datetime.now() > expires_at:
            logger.warning("Cookies expired", expires_at=expires_at.isoformat())
            path.unlink()  # Delete expired file
            return None

        cookies = data.get("cookies", [])
        logger.info("Cookies loaded", path=str(path), count=len(cookies))
        return cookies

    def clear_session(self, name: str = "default") -> None:
        """Clear saved session."""
        path = self.session_dir / f"{name}_cookies.json"
        if path.exists():
            path.unlink()
            logger.info("Session cleared", name=name)

    # =========================================================================
    # Login Flow
    # =========================================================================

    def _get_url(self, page: Page) -> str:
        """Get current URL from nodriver tab."""
        return page.target.url or ""

    async def _fill_input(self, page: Page, selector: str, value: str) -> None:
        """Find input by selector and type value."""
        element = await page.find(selector, timeout=10)
        if element is None:
            raise RuntimeError(f"Input element not found: {selector}")
        await element.clear_input()
        await element.send_keys(value)

    async def _click_element(self, page: Page, selector: str) -> None:
        """Find element by selector and click it."""
        import re

        # Handle Playwright-specific :has-text() pseudo-selector
        has_text_match = re.match(r"(.+?):has-text\(['\"](.+?)['\"]\)", selector)
        if has_text_match:
            tag = has_text_match.group(1)
            text = has_text_match.group(2)
            # Click directly via JS — evaluate can't return clickable elements
            clicked = await page.evaluate(f"""
                (() => {{
                    const els = document.querySelectorAll('{tag}');
                    for (const el of els) {{
                        const t = el.textContent.trim();
                        if (t === '{text}' || t === '{text.upper()}') {{
                            el.click();
                            return true;
                        }}
                    }}
                    return false;
                }})()
            """)
            if not clicked:
                raise RuntimeError(f"Clickable element not found: {selector}")
        else:
            element = await page.find(selector, timeout=10)
            if element is None:
                raise RuntimeError(f"Clickable element not found: {selector}")
            await element.click()

    async def _click_login_button(self, page: Page) -> None:
        """Find and click the login submit button via JS."""
        # Retry a few times in case the page hasn't fully rendered
        for attempt in range(5):
            if attempt > 0:
                await asyncio.sleep(2)
            clicked = await self._try_click_login_js(page)
            if clicked:
                logger.info("Login button clicked")
                return
        raise RuntimeError("Login button not found after retries")

    async def _try_click_login_js(self, page: Page) -> bool:
        """Attempt to click login button via JavaScript."""
        return await page.evaluate("""
            (() => {
                // Strategy 1: Find button inside the form containing password input
                const pwInput = document.querySelector("input[name='password']");
                if (pwInput) {
                    const form = pwInput.closest('form');
                    if (form) {
                        const btn = form.querySelector('button');
                        if (btn) { btn.click(); return true; }
                    }
                }
                // Strategy 2: Find button near password input (same parent container)
                if (pwInput) {
                    let container = pwInput.parentElement;
                    for (let i = 0; i < 5 && container; i++) {
                        const btn = container.querySelector('button');
                        if (btn && btn.offsetHeight > 30) {
                            btn.click();
                            return true;
                        }
                        container = container.parentElement;
                    }
                }
                // Strategy 3: Find the largest/most prominent button on the page
                const buttons = document.querySelectorAll('button');
                let bestBtn = null;
                let bestArea = 0;
                buttons.forEach(btn => {
                    const rect = btn.getBoundingClientRect();
                    const area = rect.width * rect.height;
                    if (area > bestArea && rect.width > 100) {
                        bestArea = area;
                        bestBtn = btn;
                    }
                });
                if (bestBtn) { bestBtn.click(); return true; }
                return false;
            })()
        """)

    async def _query_selector(self, page: Page, selector: str) -> Any:
        """Find element by selector, return None if not found."""
        try:
            return await page.find(selector, timeout=3)
        except Exception:
            return None

    async def login(
        self,
        browser: BrowserManager,
        username: str,
        password: str,
        session_name: str = "default",
    ) -> bool:
        """
        Perform login to Shopee.

        Args:
            browser: BrowserManager instance
            username: Shopee username/email/phone
            password: Account password
            session_name: Name to save session as

        Returns:
            True if login successful
        """
        logger.info("Starting login flow", username=username[:3] + "***")
        page = await browser.new_page()

        try:
            # Step 1: Navigate and check if already logged in
            if await self._navigate_to_login(page, browser, session_name):
                return True  # Already logged in

            # Step 2: Wait for and fill login form
            if not await self._wait_for_login_form(page, browser, session_name):
                return False

            # Step 3: Fill credentials and submit
            await self._fill_credentials(page, browser, username, password)

            # Step 4: Handle verification challenges
            await self._handle_verification_challenges(page, browser)

            # Step 5: Complete login and save session
            return await self._complete_login(page, browser, session_name)

        except Exception as e:
            logger.error("Login failed", error=str(e))
            return False

        finally:
            await browser.close_page(page)

    async def _navigate_to_login(
        self,
        page: Page,
        browser: BrowserManager,
        session_name: str,
    ) -> bool:
        """
        Navigate to login page and check if already logged in.

        Returns:
            True if already logged in, False if login form needed
        """
        max_retries = 3

        for attempt in range(max_retries):
            await browser.goto(page, LOGIN_URL, wait_until="load")
            await browser.random_delay(3.0, 5.0)  # Wait longer for JS to render

            current_url = self._get_url(page)

            if self._is_logged_in_url(current_url):
                logger.info("Already logged in (detected from redirect URL)")
                await self._save_session(browser, session_name)
                return True

            # Check if we're on the login page
            if "/buyer/login" in current_url or "/login" in current_url:
                logger.info("On login page", url=current_url)
                return False

            # If redirected to homepage, check if user is already logged in
            if current_url.rstrip("/") == self.HOME_URL.rstrip(
                "/"
            ) or current_url.startswith(self.HOME_URL):
                # Check if already logged in via Chrome profile cookies
                if await self._check_already_logged_in(page, browser):
                    logger.info("Already logged in (detected from Chrome profile)")
                    await self._save_session(browser, session_name)
                    return True

                logger.warning(
                    f"Redirected to homepage but not logged in, retrying... (attempt {attempt + 1}/{max_retries})"
                )
                await browser.random_delay(2.0, 3.0)
                continue

            # Unknown page, but not homepage - might be login variant
            logger.info("On unknown page, proceeding", url=current_url)
            return False

        logger.error("Failed to reach login page after retries")
        return False

    async def _check_already_logged_in(
        self,
        page: Page,
        browser: BrowserManager,
    ) -> bool:
        """
        Check if user is already logged in on homepage.

        Checks for:
        1. Auth cookies
        2. Username/profile element in navbar

        Returns:
            True if logged in, False otherwise
        """
        try:
            # Check 1: Look for auth cookies
            cookies = await browser.get_cookies()
            auth_cookie_names = {
                "SPC_EC",
                "SPC_ST",
                "SPC_CDS",
                "SPC_U",
                "SPC_F",
                "SPC_R_T_ID",
                "SPC_T_ID",
                "SPC_T_IV",
                "SPC_SI",
                "SPC_SEC_SI",
            }
            auth_cookies = [c for c in cookies if c.get("name") in auth_cookie_names]

            if auth_cookies:
                logger.info(
                    "Auth cookies found - user is logged in",
                    cookie_names=[c.get("name") for c in auth_cookies],
                )
                return True

            # Check 2: Look for username element in navbar
            username_selectors = [
                "[class*='navbar__username']",
                "[class*='stardust-popover'] [class*='shopee-avatar']",
                "[class*='navbar'] [class*='avatar']",
                ".navbar-link--account",
                "[data-testid='account-drawer']",
            ]

            for selector in username_selectors:
                try:
                    element = await page.find(selector, timeout=2)
                    if element:
                        logger.info(
                            f"User profile element found with selector: {selector}"
                        )
                        return True
                except Exception:
                    continue

            # Check 3: Run JS to find username in navbar
            has_username = await page.evaluate("""
                (() => {
                    // Look for navbar username text
                    const navbarText = document.querySelector('.navbar')?.textContent || '';
                    // Look for account-related elements
                    const accountEl = document.querySelector('[class*="account"]');
                    const avatarEl = document.querySelector('[class*="avatar"]');
                    // Check if there's a logged-in indicator
                    return accountEl !== null || avatarEl !== null || navbarText.includes('@');
                })()
            """)

            if has_username:
                logger.info("User appears to be logged in (detected via JS)")
                return True

            return False

        except Exception as e:
            logger.warning(f"Error checking login status: {e}")
            return False

    async def _wait_for_login_form(
        self,
        page: Page,
        browser: BrowserManager,
        session_name: str,
    ) -> bool:
        """
        Wait for login form to appear.

        Returns:
            True if form found, False otherwise
        """
        # Try primary selector first
        form_found = await browser.wait_for_selector_safe(
            page,
            self.SELECTORS["username_input"],
            timeout=15000,
        )

        # If primary selector fails, try alternatives
        if not form_found:
            logger.info("Primary selector failed, trying alternatives...")
            for selector in self.ALT_SELECTORS["username_input"]:
                form_found = await browser.wait_for_selector_safe(
                    page,
                    selector,
                    timeout=5000,
                )
                if form_found:
                    logger.info(f"Found login form with selector: {selector}")
                    # Update the selector for this session
                    self.SELECTORS["username_input"] = selector
                    break

        if not form_found:
            # Re-check URL - page may have redirected during the wait
            if self._is_logged_in_url(self._get_url(page)):
                logger.info("Already logged in (detected after form wait)")
                await self._save_session(browser, session_name)
                return False  # Return False to skip rest of login, but login succeeded

            # Log page content for debugging
            current_url = self._get_url(page)
            logger.error("Login form not found", current_url=current_url)

            # Try to detect what page we're on
            page_html = await page.evaluate("document.body.innerHTML.substring(0, 500)")
            logger.debug("Page preview", html_preview=page_html)

            return False

        return True

    async def _fill_credentials(
        self,
        page: Page,
        browser: BrowserManager,
        username: str,
        password: str,
    ) -> None:
        """Fill username and password fields and submit."""
        # Fill username
        await self._fill_input(page, self.SELECTORS["username_input"], username)
        await browser.random_delay(0.5, 1.0)

        # Try to find password field (with alternatives)
        password_filled = False
        for selector in self.ALT_SELECTORS["password_input"]:
            try:
                await self._fill_input(page, selector, password)
                password_filled = True
                logger.info(f"Password filled with selector: {selector}")
                break
            except RuntimeError:
                continue

        if not password_filled:
            raise RuntimeError("Could not find password input field")

        await browser.random_delay(0.5, 1.0)
        await self._click_login_button(page)
        await browser.random_delay(3.0, 5.0)

    async def _handle_verification_challenges(
        self,
        page: Page,
        browser: BrowserManager,
    ) -> None:
        """Handle CAPTCHA and OTP verification challenges."""
        # Handle CAPTCHA
        if await self._check_captcha(page):
            await self._handle_captcha(page, browser)

        # Handle OTP
        if await self._check_otp(page):
            await self._handle_otp(page)

        # Wait for manual completion if still on verification page
        await self._wait_for_verification_completion(page)

    async def _handle_captcha(self, page: Page, browser: BrowserManager) -> None:
        """Handle CAPTCHA challenge with auto-solve or manual fallback."""
        captcha_solved = False

        # Try auto-solve if enabled
        if self.use_anticaptcha and self.captcha_solver:
            logger.info("Attempting auto-solve with 2Captcha...")
            captcha_solved = await self.captcha_solver.solve_shopee_slider(page)

            if captcha_solved:
                logger.info("CAPTCHA auto-solved successfully!")
                await browser.random_delay(1.0, 2.0)
            else:
                logger.warning("Auto-solve failed, falling back to manual")

        # Fall back to manual if auto-solve disabled or failed
        if not captcha_solved:
            logger.warning("CAPTCHA detected - manual intervention required")
            logger.warning(
                "Please solve the CAPTCHA in the browser window (90s timeout)"
            )
            await self._wait_until_not_on_verification(page, timeout=90000)

    async def _handle_otp(self, page: Page) -> None:
        """Handle OTP verification with manual input."""
        logger.warning("OTP required - manual intervention required")
        logger.warning("Please enter OTP in the browser window (90s timeout)")
        await self._wait_until_not_on_verification(page, timeout=90000)

    async def _wait_for_verification_completion(self, page: Page) -> None:
        """Wait for user to complete any remaining verification steps."""
        current_url = self._get_url(page)
        if self._is_on_verification_page(current_url):
            logger.warning(
                "Still on login/verification page - waiting for manual completion (90s)"
            )
            await self._wait_until_not_on_verification(page, timeout=90000)

    async def _complete_login(
        self,
        page: Page,
        browser: BrowserManager,
        session_name: str,
    ) -> bool:
        """Verify login success and save session."""
        success = await self._verify_login(page, browser)

        if success:
            await self._save_session(browser, session_name)
            logger.info("Login successful")
        else:
            # Even if verification is uncertain, save cookies if we have any
            # User might have completed login manually
            current_url = self._get_url(page)
            if "/buyer/login" not in current_url and "/verify/" not in current_url:
                cookies = await browser.get_cookies()
                if cookies:
                    logger.warning(
                        "Login verification uncertain but saving cookies anyway",
                        cookie_count=len(cookies),
                        current_url=current_url,
                    )
                    await self._save_session(browser, session_name)
                    return True

            logger.error("Login verification failed")

        return success

    async def _save_session(self, browser: BrowserManager, session_name: str) -> None:
        """Save cookies and mark as logged in."""
        cookies = await browser.get_cookies()
        self.save_cookies(cookies, session_name)
        self._is_logged_in = True

    def _is_logged_in_url(self, url: str) -> bool:
        """Check if URL indicates successful login."""
        return "is_logged_in=true" in url or "is_from_login=true" in url

    def _is_on_verification_page(self, url: str) -> bool:
        """Check if on login or verification page."""
        return (
            "/buyer/login" in url or "/verify/" in url
        ) and not self._is_logged_in_url(url)

    async def _check_captcha(self, page: Page) -> bool:
        """Check if CAPTCHA is present (by URL or element)."""
        try:
            current_url = self._get_url(page)
            if "/verify/captcha" in current_url or "/verify/traffic" in current_url:
                return True

            captcha = await self._query_selector(page, self.SELECTORS["captcha"])
            return captcha is not None
        except Exception:
            return False

    async def _check_otp(self, page: Page) -> bool:
        """Check if OTP input is present."""
        try:
            otp = await self._query_selector(page, self.SELECTORS["otp_input"])
            return otp is not None
        except Exception:
            return False

    async def _wait_until_not_on_verification(
        self, page: Page, timeout: int = 60000
    ) -> bool:
        """Wait until we leave verification pages (CAPTCHA, OTP, etc.)."""
        start_time = asyncio.get_event_loop().time()
        poll_interval = 1.0

        while True:
            current_url = self._get_url(page)

            if "/verify/" not in current_url and "/buyer/login" not in current_url:
                logger.info("Left verification page successfully")
                return True

            # Also accept is_logged_in=true as success
            if "is_logged_in=true" in current_url:
                logger.info("Login succeeded (is_logged_in=true)")
                return True

            elapsed = (asyncio.get_event_loop().time() - start_time) * 1000
            if elapsed >= timeout:
                logger.warning("Timeout waiting for verification to complete")
                return False

            await asyncio.sleep(poll_interval)

    async def _verify_login(self, page: Page, browser: BrowserManager) -> bool:
        """Verify login was successful."""
        try:
            current_url = self._get_url(page)
            logger.info("Verifying login", current_url=current_url)

            # Quick check: URL indicators of successful login
            if (
                "is_from_login=true" in current_url
                or "is_logged_in=true" in current_url
            ):
                logger.info("Login success detected from URL", current_url=current_url)
                return True

            # If we're no longer on the login page, verify via cookies
            if "/buyer/login" not in current_url and "/verify/" not in current_url:
                cookies = await browser.get_cookies()

                # Log all Shopee cookies for debugging
                shopee_cookies = [
                    c for c in cookies if "shopee" in c.get("domain", "").lower()
                ]
                logger.info(
                    "Shopee cookies found",
                    count=len(shopee_cookies),
                    names=[c.get("name") for c in shopee_cookies],
                )

                # Check for known auth cookies (expanded list)
                auth_cookie_names = {
                    "SPC_EC",
                    "SPC_ST",
                    "SPC_CDS",
                    "SPC_U",
                    "SPC_F",
                    "SPC_R_T_ID",
                    "SPC_T_ID",
                    "SPC_T_IV",
                    "SPC_SI",
                    "SPC_SEC_SI",
                }
                shopee_auth_cookies = [
                    c for c in cookies if c.get("name") in auth_cookie_names
                ]

                if shopee_auth_cookies:
                    logger.info(
                        "Login verified via auth cookies",
                        cookie_count=len(shopee_auth_cookies),
                        cookie_names=[c.get("name") for c in shopee_auth_cookies],
                    )
                    return True

                # Fallback: If we're on homepage and have ANY shopee cookies,
                # consider login successful (user may have completed verification)
                if (
                    current_url.rstrip("/") == self.HOME_URL.rstrip("/")
                    or current_url.startswith(self.HOME_URL)
                ) and shopee_cookies:
                    logger.info(
                        "Login assumed successful (on homepage with Shopee cookies)",
                        cookie_count=len(shopee_cookies),
                    )
                    return True

            return False

        except Exception as e:
            logger.error("Login verification error", error=str(e))
            return False

    # =========================================================================
    # Session Restoration
    # =========================================================================

    async def restore_session(
        self,
        browser: BrowserManager,
        session_name: str = "default",
    ) -> bool:
        """
        Restore session from saved cookies.

        Args:
            browser: BrowserManager instance
            session_name: Name of saved session

        Returns:
            True if session restored and valid
        """
        logger.info("Attempting to restore session", session_name=session_name)

        cookies = self.load_cookies(session_name)
        if not cookies:
            logger.info("No saved session found")
            return False

        # Set cookies via CDP (chrome profile may not persist them reliably)
        await browser.set_cookies(cookies)

        self._is_logged_in = True
        logger.info("Session restored from saved cookies")
        return True

    # =========================================================================
    # Session Status
    # =========================================================================

    @property
    def is_logged_in(self) -> bool:
        """Check if currently logged in."""
        return self._is_logged_in

    async def ensure_logged_in(
        self,
        browser: BrowserManager,
        username: str,
        password: str,
        session_name: str = "default",
    ) -> bool:
        """
        Ensure user is logged in (restore or login).

        Args:
            browser: BrowserManager instance
            username: Shopee username
            password: Account password
            session_name: Session name

        Returns:
            True if logged in (restored or new login)
        """
        # Try to restore existing session
        if await self.restore_session(browser, session_name):
            return True

        # Perform new login
        return await self.login(browser, username, password, session_name)
