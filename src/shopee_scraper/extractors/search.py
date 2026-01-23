"""Search results extractor for Shopee."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from shopee_scraper.extractors.base import BaseExtractor
from shopee_scraper.utils.constants import BASE_URL, PRICE_DIVISOR
from shopee_scraper.utils.logging import get_logger
from shopee_scraper.utils.parsers import parse_price, parse_sold_count


if TYPE_CHECKING:
    from shopee_scraper.core.browser import BrowserManager, Page

logger = get_logger(__name__)


class SearchExtractor(BaseExtractor):
    """
    Extract search results from Shopee.

    Navigates to the actual search page and intercepts the API response
    that Shopee's own JavaScript makes. This ensures all anti-bot tokens
    are properly set by Shopee's code.
    """

    def __init__(self, browser: BrowserManager) -> None:
        """
        Initialize search extractor.

        Args:
            browser: BrowserManager instance
        """
        self.browser = browser

    async def search(
        self,
        keyword: str,
        max_pages: int = 1,
        sort_by: str = "relevancy",
    ) -> list[dict[str, Any]]:
        """
        Search products by keyword.

        Navigates to the Shopee search page and intercepts the internal
        API response made by Shopee's own JavaScript.

        Args:
            keyword: Search keyword
            max_pages: Maximum pages to scrape (60 items per page)
            sort_by: Sort order (relevancy, sales, price_asc, price_desc)

        Returns:
            List of product dictionaries
        """
        logger.info(
            "Starting search",
            keyword=keyword,
            max_pages=max_pages,
            sort_by=sort_by,
        )

        all_products: list[dict[str, Any]] = []

        # Map sort options to Shopee URL params
        sort_url_map = {
            "relevancy": "relevancy",
            "sales": "ctime",
            "price_asc": "price",
            "price_desc": "price",
        }
        order_url = "asc" if sort_by == "price_asc" else "desc"

        page = await self.browser.new_page()

        try:
            await self.browser.random_delay(1.0, 2.0)

            for page_num in range(max_pages):
                logger.info(f"Scraping page {page_num + 1}/{max_pages}")

                search_url = (
                    f"{BASE_URL}/search?keyword={quote(keyword)}"
                    f"&page={page_num}"
                    f"&sortBy={sort_url_map.get(sort_by, 'relevancy')}"
                    f"&order={order_url}"
                )

                # Navigate to search page (with retry on verify redirect)
                products_loaded = await self._navigate_with_retry(
                    page, search_url, max_retries=3
                )
                if not products_loaded:
                    current_url = page.target.url or ""
                    if "/buyer/login" in current_url:
                        logger.error(
                            "Redirected to login - run 'shopee-scraper login' first."
                        )
                    break

                # Wait for products to render and scroll to load all
                await self.browser.scroll_page(page, scroll_count=5)
                await asyncio.sleep(2)

                # Extract products from DOM
                products = await self._extract_from_dom(page)
                all_products.extend(products)
                logger.info(
                    f"Extracted {len(products)} products from page {page_num + 1}"
                )

                if len(products) < 60:
                    logger.info("No more results, stopping pagination")
                    break

                await self.browser.random_delay(2.0, 4.0)

        finally:
            await self.browser.close_page(page)

        logger.info(f"Search completed: {len(all_products)} total products")
        return all_products

    async def _navigate_with_retry(
        self, page: Page, url: str, max_retries: int = 3
    ) -> bool:
        """Navigate to URL with retry on traffic verification."""
        for attempt in range(max_retries):
            await self.browser.goto(page, url)

            current_url = page.target.url or ""

            # Login required - not recoverable
            if "/buyer/login" in current_url:
                return False

            # Not on verify page - success
            if "/verify/" not in current_url:
                return True

            # On verify page - wait briefly then retry
            logger.warning(
                f"Traffic verification (attempt {attempt + 1}/{max_retries})",
                url=current_url,
            )
            await asyncio.sleep(5)

            # Check if verify resolved on its own
            current_url = page.target.url or ""
            if "/verify/" not in current_url:
                return True

        logger.error("Traffic verification persists after retries")
        return False

    def _parse_api_response(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Parse API response into product list."""
        products = []

        # Log response structure for debugging
        top_keys = list(data.keys()) if data else []
        logger.debug(f"API response keys: {top_keys}")

        items = data.get("items", [])
        if not items:
            # Try alternate structure
            items = data.get("data", {}).get("items", [])

        for item in items:
            item_basic = item.get("item_basic", item)
            product = self.parse(item_basic)
            if product:
                products.append(product)

        return products

    async def _extract_from_dom(self, page: Page) -> list[dict[str, Any]]:
        """Extract products from page DOM using JavaScript evaluation."""
        # Use JavaScript to extract all product data at once
        raw_products = await page.evaluate("""
            (() => {
                const selectors = [
                    "[data-sqe='item']",
                    ".shopee-search-item-result__item",
                    "[class*='product-item']",
                    "li[class*='col-xs']"
                ];

                let items = [];
                for (const sel of selectors) {
                    items = document.querySelectorAll(sel);
                    if (items.length > 0) break;
                }

                const products = [];
                items.forEach(item => {
                    try {
                        // Get product link
                        const links = item.querySelectorAll('a');
                        let href = '';
                        for (const l of links) {
                            const h = l.getAttribute('href') || '';
                            if (h.match(/i\\.\\d+\\.\\d+/)) { href = h; break; }
                        }
                        const match = href.match(/i\\.(\\d+)\\.(\\d+)/);
                        if (!match) return;

                        // Extract name from URL slug (most reliable)
                        const slug = href.split('-i.')[0].replace(/^\\//,'');
                        const nameFromSlug = slug.replace(/-/g, ' ');

                        // Try DOM-based name extraction
                        const allText = item.innerText || '';
                        const lines = allText.split('\\n').filter(l => l.trim().length > 5);
                        const nameFromDom = lines[0] || '';

                        // Price: find text matching Rp pattern
                        let priceText = '0';
                        const priceMatch = allText.match(/Rp[\\s.]?([\\d.,]+)/);
                        if (priceMatch) priceText = priceMatch[0];

                        // Sold: find "terjual" or number+sold pattern
                        let soldText = '0';
                        const soldMatch = allText.match(/(\\d[\\d.,]*[rRbBjJ]*)\\s*((?:RB|rb|Rb)\\+?)?\\s*[Tt]erjual/i)
                            || allText.match(/[Tt]erjual\\s*(\\d[\\d.,]*[rRbBjJ]*)/i);
                        if (soldMatch) soldText = soldMatch[0];

                        // Get image
                        const imgEl = item.querySelector('img');
                        const image = imgEl ? (imgEl.src || imgEl.getAttribute('src') || '') : '';

                        products.push({
                            shop_id: parseInt(match[1]),
                            item_id: parseInt(match[2]),
                            name: nameFromDom || nameFromSlug,
                            price_text: priceText,
                            sold_text: soldText,
                            image: image,
                            href: href
                        });
                    } catch(e) {}
                });
                return JSON.stringify(products);
            })()
        """)

        # nodriver returns CDP serialized format; we use JSON.stringify
        # in JS and parse here to get plain dicts
        import json as _json

        if isinstance(raw_products, str):
            try:
                raw_products = _json.loads(raw_products)
            except _json.JSONDecodeError:
                raw_products = []

        products = []
        for raw in raw_products or []:
            try:
                products.append(
                    {
                        "item_id": raw["item_id"],
                        "shop_id": raw["shop_id"],
                        "name": raw["name"],
                        "price": parse_price(raw.get("price_text", "0")),
                        "sold": parse_sold_count(raw.get("sold_text", "0")),
                        "image": raw.get("image", ""),
                        "url": f"{BASE_URL}{raw['href']}" if raw.get("href") else "",
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to parse product: {e}")

        logger.debug(f"DOM extraction found {len(products)} products")
        return products

    def parse(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """Parse and structure product data from API."""
        if not raw_data:
            return {}

        # Extract basic info
        item_id = raw_data.get("itemid", raw_data.get("item_id", 0))
        shop_id = raw_data.get("shopid", raw_data.get("shop_id", 0))

        if not item_id or not shop_id:
            return {}

        # Price (Shopee stores price * 100000)
        price_raw = raw_data.get("price", 0)
        price_min = raw_data.get("price_min", price_raw)
        price_max = raw_data.get("price_max", price_raw)

        # Convert price
        price = price_min / PRICE_DIVISOR if price_min else 0
        price_max_val = price_max / PRICE_DIVISOR if price_max else price

        # Images
        images = raw_data.get("images", [])
        image_url = ""
        if images:
            image_url = f"https://cf.shopee.co.id/file/{images[0]}"

        # Build product dict
        return {
            "item_id": item_id,
            "shop_id": shop_id,
            "name": raw_data.get("name", ""),
            "price": price,
            "price_max": price_max_val,
            "price_before_discount": raw_data.get("price_before_discount", 0)
            / PRICE_DIVISOR,
            "discount": raw_data.get("raw_discount", 0),
            "stock": raw_data.get("stock", 0),
            "sold": raw_data.get("sold", raw_data.get("historical_sold", 0)),
            "rating": raw_data.get("item_rating", {}).get("rating_star", 0),
            "rating_count": sum(
                raw_data.get("item_rating", {}).get("rating_count", [0])
            ),
            "liked_count": raw_data.get("liked_count", 0),
            "shop_location": raw_data.get("shop_location", ""),
            "is_official_shop": raw_data.get("is_official_shop", False),
            "is_preferred_plus": raw_data.get("is_preferred_plus_seller", False),
            "image": image_url,
            "url": f"{BASE_URL}/product/{shop_id}/{item_id}",
            "category_id": raw_data.get("catid", 0),
        }

    async def extract(self, page: Page) -> dict[str, Any]:
        """Extract data from current page (interface compliance)."""
        products = await self._extract_from_dom(page)
        return {"products": products}
