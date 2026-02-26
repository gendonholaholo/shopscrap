"""Quick scrape test - stop after N products."""

import asyncio
from pathlib import Path

from dotenv import load_dotenv


# Load .env
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from playwright.async_api import Page  # noqa: E402

from shopee_scraper.core.browser import BrowserManager  # noqa: E402
from shopee_scraper.core.session import SessionManager  # noqa: E402
from shopee_scraper.extractors.search import SearchExtractor  # noqa: E402
from shopee_scraper.utils.captcha_solver import (  # noqa: E402
    CaptchaSolver,
    create_captcha_solver,
)
from shopee_scraper.utils.proxy import load_proxies_from_env  # noqa: E402


def print_header(keyword: str, limit: int) -> None:
    """Print test header."""
    print(f"\n{'=' * 50}")
    print(f"Scrape Test: '{keyword}' (limit: {limit} products)")
    print(f"{'=' * 50}\n")


async def load_session_cookies(page: Page, session: SessionManager) -> None:
    """Load cookies into page context."""
    print("[2/4] Loading session cookies...")
    cookies = session.load_cookies()
    if cookies:
        await page.context.add_cookies(cookies)
        print(f"      Loaded {len(cookies)} cookies")
    else:
        print("      No cookies found")


async def warm_up_session(
    page: Page, browser: BrowserManager, solver: CaptchaSolver | None
) -> None:
    """Warm up session by visiting homepage and handling verification."""
    print("[2.5/4] Warming up session (visiting homepage)...")
    await browser.goto(page, "https://shopee.co.id")
    await asyncio.sleep(3)

    if "/verify/" not in page.url:
        print("      [✓] Homepage loaded OK")
        return

    print(f"      [!] Hit verification: {page.url[:80]}")
    await _handle_verification(page, browser, solver)


async def _handle_verification(
    page: Page, browser: BrowserManager, solver: CaptchaSolver | None
) -> None:
    """Handle verification page."""
    if not (solver and solver.is_available):
        print("      [!] No solver available, waiting...")
        await asyncio.sleep(5)
        return

    print("      [*] Attempting to solve...")
    solved = await solver.solve_shopee_slider(page)
    if solved:
        print("      [✓] Verification solved!")
        await browser.goto(page, "https://shopee.co.id")
        await asyncio.sleep(2)
    else:
        print("      [✗] Could not solve verification")


def print_products(products: list[dict], all_products: list[dict]) -> None:
    """Print scraped products summary."""
    for idx, product in enumerate(products, 1):
        name = product.get("name", "N/A")
        name_display = name[:50] if name else "N/A"
        print(f"      [{idx}] {name_display}...")
        print(f"          Price: Rp {product.get('price', 0):,}")
        print(f"          Sold: {product.get('sold', 0)}")

    print(
        f"\n[✓] Got {len(products)} products (from {len(all_products)} total on page)"
    )


def print_results(products: list[dict]) -> None:
    """Print final results."""
    print("\n[4/4] Results:")
    print(f"      Total products scraped: {len(products)}")

    if not products:
        return

    print("\n      Sample data from first product:")
    p = products[0]
    for key in ["item_id", "shop_id", "name", "price", "sold", "rating"]:
        print(f"        {key}: {p.get(key, 'N/A')}")


async def test_scrape_limited(keyword: str = "laptop", limit: int = 3):
    """Scrape and stop after getting `limit` products."""
    import os

    print_header(keyword, limit)

    # Load proxy from .env
    proxy_pool = load_proxies_from_env()
    if proxy_pool.is_empty:
        print("[!] WARNING: No proxy configured. Set PROXY_ENABLED=true in .env")
    else:
        print(f"[*] Proxy loaded: {proxy_pool.size} proxy(s)")

    # Read headless from env (default: true)
    headless = os.getenv("HEADLESS", "true").lower() in ("true", "1", "yes")
    print(f"[*] Browser mode: {'headless' if headless else 'visible'}")

    browser = BrowserManager(proxy_pool=proxy_pool, headless=headless)
    session = SessionManager()
    solver = create_captcha_solver()

    products = []

    try:
        # Start browser
        print("[1/4] Starting browser...")
        await browser.start()

        # Load cookies and warm up
        page = await browser.new_page()
        await load_session_cookies(page, session)
        await warm_up_session(page, browser, solver)

        # Create extractor and scrape
        extractor = SearchExtractor(browser=browser, captcha_solver=solver)
        print(f"[3/4] Scraping '{keyword}'...")
        all_products = await extractor.search(keyword, max_pages=1)

        products = all_products[:limit]
        print_products(products, all_products)
        print_results(products)

        return products

    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        raise

    finally:
        print("\n[*] Closing browser...")
        await browser.close()


if __name__ == "__main__":
    result = asyncio.run(test_scrape_limited("laptop", limit=3))
    print(f"\n{'=' * 50}")
    print(f"RESULT: {'SUCCESS' if result else 'FAILED'} - Got {len(result)} products")
    print(f"{'=' * 50}")
