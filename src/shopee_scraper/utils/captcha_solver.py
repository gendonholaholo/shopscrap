"""CAPTCHA solver using 2Captcha service for Shopee slider verification.

Based on 2Captcha best practices:
- https://2captcha.com/blog/slider-captcha-bypass
- https://2captcha.com/api-docs/coordinates
- https://github.com/2captcha/custom-slider-demo
"""

from __future__ import annotations

import asyncio
import os
import random
from typing import TYPE_CHECKING, Any

from shopee_scraper.utils.logging import get_logger


if TYPE_CHECKING:
    from nodriver import Tab as Page

logger = get_logger(__name__)

# Puzzle piece width is typically ~40px, so we subtract half for center offset
PUZZLE_PIECE_HALF_WIDTH = 20

# Human-like drag parameters (from 2Captcha documentation)
MIN_DRAG_STEPS = 50
MAX_DRAG_STEPS = 100

# Shopee captcha selectors (updated for current DOM structure)
CAPTCHA_CANVAS_SELECTORS = [
    "canvas",
    "[class*='captcha'] canvas",
    "[class*='verify'] canvas",
    "[class*='slider'] canvas",
    "#captcha canvas",
]

SLIDER_BUTTON_SELECTORS = [
    "[class*='slider'] [class*='btn']",
    "[class*='slider-btn']",
    "[class*='drag'] [class*='btn']",
    "[class*='captcha'] button",
    "[class*='verify'] [class*='slider'] button",
    "[class*='secsdk-captcha-drag-icon']",
    "[class*='captcha-slider-btn']",
    "[class*='geetest_slider_button']",
    "div[style*='cursor: pointer'][style*='position: absolute']",
]


class CaptchaSolver:
    """
    Solves Shopee slider CAPTCHAs using 2Captcha coordinates API.

    The slider captcha requires dragging a puzzle piece to complete an image.
    We capture the canvas screenshot, send it to 2Captcha workers who identify
    the target position, then simulate a human-like drag operation.

    Best practices implemented:
    - Capture only canvas element, not full page
    - Multi-language instructions for workers
    - goodReport/badReport feedback for accuracy
    - Proper offset calculation (subtract puzzle width)
    - Human-like drag with 50-100 steps
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
        self._last_captcha_id: str | None = None

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

        Args:
            page: nodriver Tab/Page with CAPTCHA displayed

        Returns:
            True if solved successfully
        """
        if not self.is_available:
            logger.warning("CAPTCHA solver not available")
            return False

        try:
            logger.info("Attempting to solve Shopee slider CAPTCHA...")

            # Wait for captcha to fully load
            await asyncio.sleep(2)

            # Step 1: Capture only the canvas element (not full page)
            captcha_image = await self._capture_captcha_canvas(page)
            if not captcha_image:
                # Fallback to full page if canvas not found
                logger.warning("Canvas not found, falling back to full page screenshot")
                captcha_image = await self._capture_full_page(page)

            if not captcha_image:
                logger.error("Failed to capture CAPTCHA image")
                return False

            # Step 2: Send to 2Captcha with proper instructions
            coordinates = await self._get_target_coordinates(captcha_image)
            if not coordinates:
                logger.error("2Captcha failed to solve")
                return False

            # Step 3: Perform slider drag with proper offset
            success = await self._perform_slider_drag(page, coordinates)

            # Step 4: Report result to 2Captcha for accuracy improvement
            await self._report_result(success)

            if success:
                logger.info("CAPTCHA solved successfully!")
            else:
                logger.warning("Failed to apply CAPTCHA solution")

            return success

        except Exception as e:
            logger.error(f"CAPTCHA solving error: {e}")
            await self._report_result(False)
            return False

    async def _capture_captcha_canvas(self, page: Page) -> str | None:
        """
        Capture only the captcha canvas element as base64.

        This is more accurate than full page screenshot because workers
        see only the relevant puzzle image.
        """
        try:
            # Try to find and capture the canvas element
            for selector in CAPTCHA_CANVAS_SELECTORS:
                try:
                    canvas_data = await page.evaluate(f"""
                        (() => {{
                            const canvas = document.querySelector('{selector}');
                            if (canvas && canvas.toDataURL) {{
                                const dataUrl = canvas.toDataURL('image/png');
                                // Validate the data URL is not empty/corrupted
                                if (dataUrl && dataUrl.length > 2000) {{
                                    return dataUrl.replace('data:image/png;base64,', '');
                                }}
                            }}
                            return null;
                        }})()
                    """)

                    if canvas_data:
                        logger.info(
                            f"Canvas captured with selector: {selector}",
                            size=len(canvas_data),
                        )
                        return canvas_data

                except Exception as e:
                    logger.debug(f"Canvas selector {selector} failed: {e}")
                    continue

            # Try alternative: capture any visible canvas
            canvas_data = await page.evaluate("""
                (() => {
                    const canvases = document.querySelectorAll('canvas');
                    for (const canvas of canvases) {
                        const rect = canvas.getBoundingClientRect();
                        // Look for reasonably sized captcha canvas (not tiny icons)
                        if (rect.width > 200 && rect.height > 100) {
                            const dataUrl = canvas.toDataURL('image/png');
                            if (dataUrl && dataUrl.length > 2000) {
                                return dataUrl.replace('data:image/png;base64,', '');
                            }
                        }
                    }
                    return null;
                })()
            """)

            if canvas_data:
                logger.info(
                    "Canvas captured via size-based detection", size=len(canvas_data)
                )
                return canvas_data

            return None

        except Exception as e:
            logger.error(f"Failed to capture canvas: {e}")
            return None

    async def _capture_full_page(self, page: Page) -> str | None:
        """Capture full page screenshot as fallback."""
        try:
            import nodriver.cdp.page as cdp_page

            result = await page.send(cdp_page.capture_screenshot(format_="png"))
            logger.debug(
                "Full page screenshot captured", size=len(result) if result else 0
            )
            return result

        except Exception as e:
            logger.error(f"Failed to capture full page: {e}")
            return None

    async def _get_target_coordinates(self, image_base64: str) -> dict[str, Any] | None:
        """
        Send image to 2Captcha and get target coordinates.

        Uses multi-language instructions for better accuracy.

        Returns:
            dict with 'x', 'y' coordinates and 'captcha_id'
        """
        if self._solver is None:
            return None

        try:
            loop = asyncio.get_event_loop()
            solver = self._solver

            def solve() -> Any:
                # Use coordinates method with clear, multi-language instructions
                # This helps workers from different countries understand the task
                return solver.coordinates(
                    image_base64,
                    lang="en",
                    textinstructions=(
                        "Click the CENTER of the puzzle piece (the missing part). "
                        "| Klik TENGAH potongan puzzle (bagian yang hilang). "
                        "| 点击拼图块的中心位置"
                    ),
                )

            result = await loop.run_in_executor(None, solve)
            logger.info(f"2Captcha response: {result}")

            # Store captcha ID for reporting
            if isinstance(result, dict):
                self._last_captcha_id = result.get("captchaId")

            # Parse coordinates from response
            # Response format: {'captchaId': '123', 'code': 'coordinates:x=123,y=456'}
            if isinstance(result, dict) and "code" in result:
                code = result["code"]
                if code.startswith("coordinates:"):
                    coords_str = code.replace("coordinates:", "")
                    coords: dict[str, Any] = {}
                    for part in coords_str.split(","):
                        key, val = part.split("=")
                        coords[key.strip()] = int(val.strip())

                    # Add captcha_id for reporting
                    coords["captcha_id"] = result.get("captchaId")
                    return coords

            return None

        except Exception as e:
            logger.error(f"2Captcha API error: {e}")
            return None

    async def _report_result(self, success: bool) -> None:
        """
        Report solve result to 2Captcha for accuracy improvement.

        Good reports help train workers, bad reports flag problematic solutions.
        """
        if not self._solver or not self._last_captcha_id:
            return

        try:
            loop = asyncio.get_event_loop()
            solver = self._solver
            captcha_id = self._last_captcha_id

            def report() -> None:
                if success:
                    solver.report(captcha_id, True)  # goodReport
                    logger.debug(f"Reported good result for captcha {captcha_id}")
                else:
                    solver.report(captcha_id, False)  # badReport
                    logger.debug(f"Reported bad result for captcha {captcha_id}")

            await loop.run_in_executor(None, report)

        except Exception as e:
            logger.debug(f"Failed to report result: {e}")

        finally:
            self._last_captcha_id = None

    async def _perform_slider_drag(
        self, page: Page, target_coords: dict[str, Any]
    ) -> bool:
        """
        Perform slider drag operation based on captcha type.

        Applies proper offset calculation (subtract half puzzle width).

        Args:
            page: nodriver Tab/Page
            target_coords: Dict with 'x' (and optionally 'y') coordinates
        """
        try:
            # Find the slider handle element
            slider = await self._find_slider_element(page)

            if slider:
                # Slider found - perform drag operation
                position = await slider.get_position()
                if not position or not position.center:
                    logger.warning("Could not get slider position")
                    return False

                start_x, start_y = position.center
                raw_target_x = target_coords.get("x", start_x + 200)

                # IMPORTANT: Subtract half puzzle width for accurate positioning
                # The worker clicks the CENTER of the puzzle piece, but we need
                # to drag to where the LEFT EDGE should align
                target_x = raw_target_x - PUZZLE_PIECE_HALF_WIDTH

                # Calculate drag distance
                drag_distance = target_x - start_x
                logger.info(
                    f"Dragging slider: start={start_x}, raw_target={raw_target_x}, "
                    f"adjusted_target={target_x}, distance={drag_distance}"
                )

                # Simulate human-like drag with many small steps
                await self._simulate_drag(page, start_x, start_y, drag_distance)

            else:
                # No slider - try click-to-verify at coordinates
                logger.info("No slider found, trying click-to-verify approach")
                target_x = target_coords.get("x", 0)
                target_y = target_coords.get("y", 0)

                if target_x and target_y:
                    logger.info(f"Clicking at coordinates: ({target_x}, {target_y})")
                    await self._click_at_coordinates(page, target_x, target_y)
                else:
                    logger.warning("No valid coordinates for click-to-verify")
                    return False

            # Wait and check result
            await asyncio.sleep(2)

            # Check if CAPTCHA was solved (URL should change)
            current_url = page.target.url or ""
            return "/verify/" not in current_url

        except Exception as e:
            logger.error(f"Failed to perform captcha action: {e}")
            return False

    async def _find_slider_element(self, page: Page) -> Any:
        """Find the slider button/handle element."""
        # Try CSS selectors
        for selector in SLIDER_BUTTON_SELECTORS:
            try:
                element = await page.find(selector, timeout=2)
                if element:
                    logger.debug(f"Found slider with selector: {selector}")
                    return element
            except Exception:
                continue

        # Fallback: find by JavaScript with better heuristics
        try:
            result = await page.evaluate("""
                (() => {
                    // Strategy 1: Look for elements with drag-related classes
                    const dragSelectors = [
                        '[class*="slider"]',
                        '[class*="drag"]',
                        '[class*="captcha"] [class*="btn"]',
                        '[class*="secsdk"]'
                    ];

                    for (const sel of dragSelectors) {
                        const elements = document.querySelectorAll(sel);
                        for (const el of elements) {
                            const rect = el.getBoundingClientRect();
                            const style = window.getComputedStyle(el);
                            // Slider buttons are typically:
                            // - Small width (30-80px)
                            // - Small height (30-60px)
                            // - Have pointer cursor or are draggable
                            if (rect.width > 20 && rect.width < 100 &&
                                rect.height > 20 && rect.height < 80 &&
                                (style.cursor === 'pointer' || style.cursor === 'grab' ||
                                 el.draggable || el.getAttribute('draggable'))) {
                                return {
                                    found: true,
                                    x: rect.x + rect.width / 2,
                                    y: rect.y + rect.height / 2,
                                    width: rect.width,
                                    height: rect.height
                                };
                            }
                        }
                    }

                    // Strategy 2: Look for small positioned elements near bottom of captcha
                    const captcha = document.querySelector('[class*="captcha"], [class*="verify"]');
                    if (captcha) {
                        const captchaRect = captcha.getBoundingClientRect();
                        const allElements = captcha.querySelectorAll('*');
                        for (const el of allElements) {
                            const rect = el.getBoundingClientRect();
                            // Element should be near bottom of captcha
                            if (rect.y > captchaRect.y + captchaRect.height * 0.7 &&
                                rect.width > 20 && rect.width < 100 &&
                                rect.height > 20 && rect.height < 80) {
                                return {
                                    found: true,
                                    x: rect.x + rect.width / 2,
                                    y: rect.y + rect.height / 2,
                                    width: rect.width,
                                    height: rect.height
                                };
                            }
                        }
                    }

                    return { found: false };
                })()
            """)

            if isinstance(result, dict) and result.get("found"):
                logger.debug(
                    f"Found slider via JS: pos=({result['x']}, {result['y']}), "
                    f"size=({result['width']}x{result['height']})"
                )

                # Return a mock object with position
                class MockElement:
                    async def get_position(self) -> Any:
                        class Pos:
                            center = (result["x"], result["y"])

                        return Pos()

                return MockElement()

        except Exception as e:
            logger.debug(f"JS slider search error: {e}")

        return None

    async def _simulate_drag(
        self,
        page: Page,
        start_x: float,
        start_y: float,
        distance: float,
    ) -> None:
        """
        Simulate human-like drag operation.

        Uses 50-100 steps as recommended by 2Captcha documentation
        for realistic mouse movement that won't trigger bot detection.
        """
        import nodriver.cdp.input_ as cdp_input

        # Move to start position
        await page.send(
            cdp_input.dispatch_mouse_event(
                type_="mouseMoved",
                x=start_x,
                y=start_y,
            )
        )
        await asyncio.sleep(random.uniform(0.1, 0.2))

        # Mouse down
        await page.send(
            cdp_input.dispatch_mouse_event(
                type_="mousePressed",
                x=start_x,
                y=start_y,
                button=cdp_input.MouseButton.LEFT,
                click_count=1,
            )
        )
        await asyncio.sleep(random.uniform(0.05, 0.15))

        # Drag with many small steps (50-100 for human-like movement)
        steps = random.randint(MIN_DRAG_STEPS, MAX_DRAG_STEPS)
        for i in range(1, steps + 1):
            progress = i / steps

            # Ease-out curve for natural deceleration
            eased_progress = 1 - (1 - progress) ** 3

            current_x = start_x + (distance * eased_progress)

            # Add realistic vertical wobble (humans aren't perfectly horizontal)
            wobble_y = start_y + random.uniform(-3, 3)

            await page.send(
                cdp_input.dispatch_mouse_event(
                    type_="mouseMoved",
                    x=current_x,
                    y=wobble_y,
                    button=cdp_input.MouseButton.LEFT,
                    buttons=1,
                )
            )

            # Variable delay between movements (faster in middle, slower at edges)
            if progress < 0.2 or progress > 0.8:
                await asyncio.sleep(random.uniform(0.02, 0.04))
            else:
                await asyncio.sleep(random.uniform(0.008, 0.02))

        # Small pause before release (humans don't release instantly)
        await asyncio.sleep(random.uniform(0.05, 0.15))

        # Mouse up at final position
        final_x = start_x + distance
        await page.send(
            cdp_input.dispatch_mouse_event(
                type_="mouseReleased",
                x=final_x,
                y=start_y,
                button=cdp_input.MouseButton.LEFT,
                click_count=1,
            )
        )

        logger.debug(f"Drag completed: {start_x:.1f} -> {final_x:.1f} in {steps} steps")

    async def _click_at_coordinates(self, page: Page, x: float, y: float) -> None:
        """Click at specific coordinates with human-like behavior."""
        import nodriver.cdp.input_ as cdp_input

        # Add slight randomness to click position (humans aren't pixel-perfect)
        x = x + random.uniform(-3, 3)
        y = y + random.uniform(-3, 3)

        # Move to position with slight curve
        await page.send(
            cdp_input.dispatch_mouse_event(
                type_="mouseMoved",
                x=x,
                y=y,
            )
        )
        await asyncio.sleep(random.uniform(0.1, 0.3))

        # Click down
        await page.send(
            cdp_input.dispatch_mouse_event(
                type_="mousePressed",
                x=x,
                y=y,
                button=cdp_input.MouseButton.LEFT,
                click_count=1,
            )
        )
        await asyncio.sleep(random.uniform(0.05, 0.15))

        # Click up
        await page.send(
            cdp_input.dispatch_mouse_event(
                type_="mouseReleased",
                x=x,
                y=y,
                button=cdp_input.MouseButton.LEFT,
                click_count=1,
            )
        )

        logger.debug(f"Click completed at ({x:.1f}, {y:.1f})")

    def get_balance(self) -> float | None:
        """Get 2Captcha account balance."""
        if not self.is_available or self._solver is None:
            return None
        try:
            return float(self._solver.balance())
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return None


def create_captcha_solver(
    api_key: str | None = None,
    enabled: bool = True,
) -> CaptchaSolver | None:
    """
    Create a CaptchaSolver instance.

    Args:
        api_key: 2Captcha API key (or from env CAPTCHA_API_KEY/TWOCAPTCHA_API_KEY)
        enabled: Whether to enable auto-solving

    Returns:
        CaptchaSolver instance or None if disabled/no key
    """
    if not enabled:
        return None

    # Check multiple env var names for API key
    key = api_key or os.getenv("CAPTCHA_API_KEY") or os.getenv("TWOCAPTCHA_API_KEY", "")
    if not key:
        logger.info("No 2Captcha API key provided, auto-solve disabled")
        return None

    return CaptchaSolver(api_key=key, enabled=True)
