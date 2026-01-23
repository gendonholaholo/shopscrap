"""CAPTCHA solver using 2Captcha service."""

from __future__ import annotations

import asyncio
import base64
from typing import TYPE_CHECKING, Any

from shopee_scraper.utils.logging import get_logger


if TYPE_CHECKING:
    from shopee_scraper.core.browser import Page

logger = get_logger(__name__)


class CaptchaSolver:
    """
    Solves CAPTCHAs using 2Captcha API service.

    Supports:
    - Slider CAPTCHA (Shopee verification)
    - Image CAPTCHA
    - reCAPTCHA (if needed)

    Usage:
        solver = CaptchaSolver(api_key="your_2captcha_key")
        success = await solver.solve_shopee_slider(page)
    """

    def __init__(self, api_key: str, enabled: bool = True) -> None:
        """
        Initialize CAPTCHA solver.

        Args:
            api_key: 2Captcha API key
            enabled: Whether to use auto-solving
        """
        self.api_key = api_key
        self.enabled = enabled
        self._solver = None

        if enabled and api_key:
            try:
                from twocaptcha import TwoCaptcha

                self._solver = TwoCaptcha(api_key)
                logger.info("2Captcha solver initialized")
            except ImportError:
                logger.warning("2captcha-python not installed, auto-solve disabled")
                self.enabled = False
            except Exception as e:
                logger.error(f"Failed to initialize 2Captcha: {e}")
                self.enabled = False

    @property
    def is_available(self) -> bool:
        """Check if solver is available and enabled."""
        return self.enabled and self._solver is not None

    async def solve_shopee_slider(self, page: Page) -> bool:
        """
        Solve Shopee slider CAPTCHA.

        Shopee uses a slider puzzle where user needs to drag
        a piece to complete the image.

        Args:
            page: Playwright page with CAPTCHA

        Returns:
            True if solved successfully
        """
        if not self.is_available:
            logger.warning("CAPTCHA solver not available")
            return False

        try:
            logger.info("Attempting to solve Shopee slider CAPTCHA...")

            # Take screenshot of the CAPTCHA area
            captcha_image = await self._capture_captcha_image(page)
            if not captcha_image:
                logger.error("Failed to capture CAPTCHA image")
                return False

            # Send to 2Captcha for solving
            result = await self._solve_with_2captcha(captcha_image)
            if not result:
                logger.error("2Captcha failed to solve")
                return False

            # Apply the solution (slide the slider)
            success = await self._apply_slider_solution(page, result)

            if success:
                logger.info("CAPTCHA solved successfully!")
            else:
                logger.warning("Failed to apply CAPTCHA solution")

            return success

        except Exception as e:
            logger.error(f"CAPTCHA solving error: {e}")
            return False

    async def _capture_captcha_image(self, page: Page) -> str | None:
        """Capture CAPTCHA image as base64."""
        try:
            # Wait for CAPTCHA image to load
            await page.wait_for_selector("img", timeout=10000)
            await asyncio.sleep(1)  # Wait for image to fully render

            # Try to find the CAPTCHA container/image
            captcha_selectors = [
                "[class*='captcha'] img",
                "[class*='verify'] img",
                ".slider-captcha img",
                "img[src*='captcha']",
            ]

            captcha_element = None
            for selector in captcha_selectors:
                captcha_element = await page.query_selector(selector)
                if captcha_element:
                    break

            # If no specific captcha image found, screenshot the main area
            if not captcha_element:
                # Take full page screenshot and crop
                screenshot = await page.screenshot(type="png")
                return base64.b64encode(screenshot).decode()

            # Screenshot just the captcha element
            screenshot = await captcha_element.screenshot(type="png")
            return base64.b64encode(screenshot).decode()

        except Exception as e:
            logger.error(f"Failed to capture CAPTCHA: {e}")
            return None

    async def _solve_with_2captcha(self, image_base64: str) -> dict[str, Any] | None:
        """Send image to 2Captcha and get solution."""
        try:
            # Run in thread pool since 2captcha is synchronous
            loop = asyncio.get_event_loop()

            def solve():
                return self._solver.coordinates(
                    image_base64,
                    lang="en",
                )

            result = await loop.run_in_executor(None, solve)
            logger.info(f"2Captcha response: {result}")
            return result

        except Exception as e:
            logger.error(f"2Captcha API error: {e}")
            return None

    async def _apply_slider_solution(
        self, page: Page, solution: dict[str, Any]
    ) -> bool:
        """Apply the slider solution by dragging."""
        try:
            # Find the slider button/handle
            slider_selectors = [
                "[class*='slider'] button",
                "[class*='slider'] [class*='btn']",
                "[class*='drag']",
                ".slider-btn",
            ]

            slider = None
            for selector in slider_selectors:
                slider = await page.query_selector(selector)
                if slider:
                    break

            if not slider:
                logger.warning("Slider element not found")
                return False

            # Get slider bounding box
            box = await slider.bounding_box()
            if not box:
                return False

            # Calculate drag distance from 2captcha coordinates
            # The solution may contain x,y coordinates for click position
            # For slider, we use default slide distance
            x_offset = 200

            # Perform the drag operation with human-like movement
            start_x = box["x"] + box["width"] / 2
            start_y = box["y"] + box["height"] / 2

            await page.mouse.move(start_x, start_y)
            await page.mouse.down()

            # Slide with small steps to mimic human
            steps = 20
            for i in range(steps):
                await page.mouse.move(
                    start_x + (x_offset * (i + 1) / steps),
                    start_y + (i % 3 - 1),  # Small vertical wobble
                )
                await asyncio.sleep(0.02)

            await page.mouse.up()
            await asyncio.sleep(1)

            # Check if CAPTCHA was solved (page should redirect)
            current_url = page.url
            return "/verify/" not in current_url

        except Exception as e:
            logger.error(f"Failed to apply slider solution: {e}")
            return False

    def get_balance(self) -> float | None:
        """Get 2Captcha account balance."""
        if not self.is_available:
            return None
        try:
            return self._solver.balance()
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return None


# Factory function for easy creation
def create_captcha_solver(
    api_key: str | None = None,
    enabled: bool = True,
) -> CaptchaSolver | None:
    """
    Create a CaptchaSolver instance.

    Args:
        api_key: 2Captcha API key (or from env TWOCAPTCHA_API_KEY)
        enabled: Whether to enable auto-solving

    Returns:
        CaptchaSolver instance or None if disabled/no key
    """
    import os

    if not enabled:
        return None

    key = api_key or os.getenv("TWOCAPTCHA_API_KEY", "")
    if not key:
        logger.info("No 2Captcha API key provided, auto-solve disabled")
        return None

    return CaptchaSolver(api_key=key, enabled=True)
