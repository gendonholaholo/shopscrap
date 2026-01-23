"""Product detail extractor for Shopee."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from shopee_scraper.extractors.base import BaseExtractor
from shopee_scraper.utils.constants import (
    BASE_URL,
    ITEM_API,
    PRICE_DIVISOR,
    PRODUCT_API,
)
from shopee_scraper.utils.logging import get_logger
from shopee_scraper.utils.parsers import parse_price, parse_rating


if TYPE_CHECKING:
    from shopee_scraper.core.browser import BrowserManager, Page

# Type alias for nodriver response (placeholder for product extractor refactoring)
Response = object

logger = get_logger(__name__)


class ProductExtractor(BaseExtractor):
    """
    Extract product details from Shopee.

    Uses Shopee's internal API v4:
    - /api/v4/pdp/get_pc - Product detail for PC/web
    - /api/v4/item/get - Alternative endpoint
    """

    def __init__(self, browser: BrowserManager) -> None:
        """
        Initialize product extractor.

        Args:
            browser: BrowserManager instance
        """
        self.browser = browser
        self._intercepted_data: dict[str, Any] = {}

    async def get_product(
        self,
        shop_id: int,
        item_id: int,
    ) -> dict[str, Any]:
        """
        Get product detail by shop_id and item_id.

        Args:
            shop_id: Shop ID
            item_id: Item ID

        Returns:
            Product detail dictionary
        """
        logger.info("Getting product detail", shop_id=shop_id, item_id=item_id)

        page = await self.browser.new_page()
        self._intercepted_data.clear()

        try:
            # Setup response interception
            page.on("response", self._handle_response)

            # Build product URL
            product_url = f"{BASE_URL}/product/{shop_id}/{item_id}"

            # Navigate to product page
            await self.browser.goto(page, product_url)

            # Scroll to load all content
            await self.browser.scroll_page(page, scroll_count=2)

            # Wait for API response
            await self.browser.random_delay(1.0, 2.0)

            # Extract from intercepted API response
            if self._intercepted_data:
                product = self.parse(self._intercepted_data)
                logger.info("Product extracted successfully", item_id=item_id)
                return product

            # Fallback: extract from DOM
            logger.warning("API interception failed, using DOM extraction")
            return await self._extract_from_dom(page, shop_id, item_id)

        finally:
            await self.browser.close_page(page)

    async def get_products_batch(
        self,
        items: list[tuple[int, int]],
    ) -> list[dict[str, Any]]:
        """
        Get multiple products in batch.

        Args:
            items: List of (shop_id, item_id) tuples

        Returns:
            List of product dictionaries
        """
        products = []

        for shop_id, item_id in items:
            try:
                product = await self.get_product(shop_id, item_id)
                if product:
                    products.append(product)

                # Rate limiting
                await self.browser.random_delay(2.0, 4.0)

            except Exception as e:
                logger.error(
                    "Failed to get product",
                    shop_id=shop_id,
                    item_id=item_id,
                    error=str(e),
                )

        logger.info(f"Batch completed: {len(products)}/{len(items)} products")
        return products

    async def _handle_response(self, response: Response) -> None:
        """Handle intercepted API responses."""
        url = response.url

        if (PRODUCT_API in url or ITEM_API in url) and response.status == 200:
            try:
                data = await response.json()
                # Merge data from different endpoints
                if "data" in data:
                    self._intercepted_data.update(data.get("data", {}))
                elif "item" in data:
                    self._intercepted_data.update(data.get("item", {}))
                else:
                    self._intercepted_data.update(data)
                logger.debug("Intercepted product API response")
            except Exception as e:
                logger.warning(f"Failed to parse API response: {e}")

    async def _extract_from_dom(
        self,
        page: Page,
        shop_id: int,
        item_id: int,
    ) -> dict[str, Any]:
        """Fallback: Extract product from page DOM."""
        try:
            # Extract structured data from script tag
            scripts = await page.query_selector_all(
                "script[type='application/ld+json']"
            )
            for script in scripts:
                content = await script.inner_text()
                try:
                    data = json.loads(content)
                    if data.get("@type") == "Product":
                        return self._parse_structured_data(data, shop_id, item_id)
                except json.JSONDecodeError:
                    continue

            # Manual extraction
            product = {
                "item_id": item_id,
                "shop_id": shop_id,
                "url": f"{BASE_URL}/product/{shop_id}/{item_id}",
            }

            # Name
            name_el = await page.query_selector("[class*='product-title'], h1")
            if name_el:
                product["name"] = await name_el.inner_text()

            # Price
            price_el = await page.query_selector("[class*='price'] span")
            if price_el:
                price_text = await price_el.inner_text()
                product["price"] = parse_price(price_text)

            # Rating
            rating_el = await page.query_selector("[class*='rating']")
            if rating_el:
                rating_text = await rating_el.inner_text()
                product["rating"] = parse_rating(rating_text)

            # Images
            img_els = await page.query_selector_all("[class*='product-image'] img")
            product["images"] = []
            for img in img_els[:5]:  # Limit to 5 images
                src = await img.get_attribute("src")
                if src:
                    product["images"].append(src)

            return product

        except Exception as e:
            logger.error(f"DOM extraction failed: {e}")
            return {}

    def _parse_structured_data(
        self,
        data: dict[str, Any],
        shop_id: int,
        item_id: int,
    ) -> dict[str, Any]:
        """Parse JSON-LD structured data."""
        offers = data.get("offers", {})

        return {
            "item_id": item_id,
            "shop_id": shop_id,
            "name": data.get("name", ""),
            "description": data.get("description", ""),
            "price": float(offers.get("price", 0)),
            "currency": offers.get("priceCurrency", "IDR"),
            "availability": offers.get("availability", ""),
            "image": data.get("image", ""),
            "brand": data.get("brand", {}).get("name", ""),
            "rating": float(data.get("aggregateRating", {}).get("ratingValue", 0)),
            "rating_count": int(data.get("aggregateRating", {}).get("reviewCount", 0)),
            "url": f"{BASE_URL}/product/{shop_id}/{item_id}",
        }

    def parse(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """Parse and structure product data from API."""
        if not raw_data:
            return {}

        # Get item info
        item = raw_data.get("item", raw_data)

        item_id = item.get("itemid", item.get("item_id", 0))
        shop_id = item.get("shopid", item.get("shop_id", 0))

        if not item_id:
            return {}

        # Price (Shopee stores price * 100000)
        price_raw = item.get("price", 0)
        price_min = item.get("price_min", price_raw)
        price_max = item.get("price_max", price_raw)

        price = price_min / PRICE_DIVISOR if price_min else 0
        price_max_val = price_max / PRICE_DIVISOR if price_max else price

        # Images
        images = item.get("images", [])
        image_urls = [f"https://cf.shopee.co.id/file/{img}" for img in images]

        # Variants/Models
        models = item.get("models", [])
        variants = []
        for model in models:
            variants.append(
                {
                    "model_id": model.get("modelid", 0),
                    "name": model.get("name", ""),
                    "price": model.get("price", 0) / PRICE_DIVISOR,
                    "stock": model.get("stock", 0),
                    "sold": model.get("sold", 0),
                }
            )

        # Categories
        categories = item.get("categories", [])
        category_path = [cat.get("display_name", "") for cat in categories]

        # Tier variations (size, color, etc.)
        tier_variations = item.get("tier_variations", [])
        variations = []
        for tier in tier_variations:
            variations.append(
                {
                    "name": tier.get("name", ""),
                    "options": tier.get("options", []),
                }
            )

        # Shop info
        shop_info = raw_data.get("shop_info", {})

        # Build product dict
        return {
            "item_id": item_id,
            "shop_id": shop_id,
            "name": item.get("name", ""),
            "description": item.get("description", ""),
            "price": price,
            "price_min": price,
            "price_max": price_max_val,
            "price_before_discount": item.get("price_before_discount", 0)
            / PRICE_DIVISOR,
            "discount": item.get("raw_discount", item.get("discount", 0)),
            "stock": item.get("stock", 0),
            "sold": item.get("sold", item.get("historical_sold", 0)),
            "rating": item.get("item_rating", {}).get("rating_star", 0),
            "rating_count": item.get("cmt_count", 0),
            "rating_breakdown": item.get("item_rating", {}).get("rating_count", []),
            "liked_count": item.get("liked_count", 0),
            "view_count": item.get("view_count", 0),
            "images": image_urls,
            "video": item.get("video_info_list", []),
            "variants": variants,
            "variations": variations,
            "category_id": item.get("catid", 0),
            "category_path": category_path,
            "brand": item.get("brand", ""),
            "condition": "new" if item.get("is_new", True) else "used",
            "shop": {
                "shop_id": shop_id,
                "name": shop_info.get("name", ""),
                "username": shop_info.get("account", {}).get("username", ""),
                "location": shop_info.get("shop_location", ""),
                "rating": shop_info.get("rating_star", 0),
                "response_rate": shop_info.get("response_rate", 0),
                "response_time": shop_info.get("response_time", 0),
                "follower_count": shop_info.get("follower_count", 0),
                "is_official": shop_info.get("is_official_shop", False),
                "is_preferred_plus": shop_info.get("is_preferred_plus_seller", False),
            },
            "attributes": item.get("attributes", []),
            "url": f"{BASE_URL}/product/{shop_id}/{item_id}",
            "created_at": item.get("ctime", 0),
            "updated_at": item.get("mtime", 0),
        }

    async def extract(self, page: Page) -> dict[str, Any]:
        """Extract data from current page (interface compliance)."""
        # Parse URL to get shop_id and item_id
        url = page.url
        match = re.search(r"/product/(\d+)/(\d+)", url)
        if match:
            shop_id = int(match.group(1))
            item_id = int(match.group(2))
            return await self._extract_from_dom(page, shop_id, item_id)
        return {}
