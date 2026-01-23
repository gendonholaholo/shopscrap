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

        Uses DOM extraction since nodriver doesn't support response interception.

        Args:
            shop_id: Shop ID
            item_id: Item ID

        Returns:
            Product detail dictionary
        """
        logger.info("Getting product detail", shop_id=shop_id, item_id=item_id)

        page = await self.browser.new_page()

        try:
            # Build product URL
            product_url = f"{BASE_URL}/product/{shop_id}/{item_id}"

            # Navigate to product page
            await self.browser.goto(page, product_url)

            # Scroll to load all content
            await self.browser.scroll_page(page, scroll_count=3)

            # Wait for page to fully load
            await self.browser.random_delay(2.0, 3.0)

            # Extract from DOM using JavaScript
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
        """Extract product from page DOM using JavaScript evaluation."""
        try:
            # Use JavaScript to extract all product data at once
            raw_data = await page.evaluate("""
                (() => {
                    const result = {
                        name: '',
                        description: '',
                        price: 0,
                        price_text: '',
                        stock: 0,
                        sold: 0,
                        rating: 0,
                        rating_count: 0,
                        images: [],
                        shop_name: '',
                        shop_location: '',
                        is_official: false,
                        category_path: [],
                        variations: [],
                        attributes: []
                    };

                    // Try JSON-LD structured data first
                    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                    for (const script of scripts) {
                        try {
                            const data = JSON.parse(script.textContent);
                            if (data['@type'] === 'Product') {
                                result.name = data.name || '';
                                result.description = data.description || '';
                                if (data.offers) {
                                    result.price = parseFloat(data.offers.price) || 0;
                                }
                                if (data.aggregateRating) {
                                    result.rating = parseFloat(data.aggregateRating.ratingValue) || 0;
                                    result.rating_count = parseInt(data.aggregateRating.reviewCount) || 0;
                                }
                                if (data.image) {
                                    result.images = Array.isArray(data.image) ? data.image : [data.image];
                                }
                            }
                        } catch(e) {}
                    }

                    // Extract from page content if JSON-LD is incomplete
                    const allText = document.body.innerText || '';

                    // Name from title or h1
                    if (!result.name) {
                        const titleEl = document.querySelector('h1, [class*="product-title"], [class*="title"]');
                        if (titleEl) result.name = titleEl.innerText.trim();
                    }

                    // Price
                    if (!result.price) {
                        const priceMatch = allText.match(/Rp\\s*([\\d.,]+)/);
                        if (priceMatch) {
                            result.price_text = priceMatch[0];
                            result.price = parseFloat(priceMatch[1].replace(/\\./g, '').replace(',', '.')) || 0;
                        }
                    }

                    // Stock
                    const stockMatch = allText.match(/(?:Stok|Stock)[:\\s]*(\\d+)/i);
                    if (stockMatch) result.stock = parseInt(stockMatch[1]) || 0;

                    // Sold
                    const soldMatch = allText.match(/(\\d+[\\d.,]*[kKrRbB]*)\\s*(?:Terjual|sold)/i);
                    if (soldMatch) {
                        let sold = soldMatch[1].toLowerCase();
                        if (sold.includes('rb') || sold.includes('k')) {
                            result.sold = parseFloat(sold) * 1000;
                        } else {
                            result.sold = parseInt(sold.replace(/\\./g, '')) || 0;
                        }
                    }

                    // Rating
                    if (!result.rating) {
                        const ratingMatch = allText.match(/(\\d+[.,]?\\d*)\\s*(?:\\/\\s*5|dari\\s*5|out of 5)/i);
                        if (ratingMatch) result.rating = parseFloat(ratingMatch[1].replace(',', '.')) || 0;
                    }

                    // Images
                    if (result.images.length === 0) {
                        const imgEls = document.querySelectorAll('[class*="product"] img, [class*="gallery"] img, [class*="carousel"] img');
                        imgEls.forEach(img => {
                            const src = img.src || img.getAttribute('src');
                            if (src && src.includes('shopee') && !src.includes('thumb') && result.images.length < 8) {
                                result.images.push(src);
                            }
                        });
                    }

                    // Shop info
                    const shopEl = document.querySelector('[class*="shop-name"], [class*="seller-name"]');
                    if (shopEl) result.shop_name = shopEl.innerText.trim();

                    const locEl = document.querySelector('[class*="location"], [class*="shop-location"]');
                    if (locEl) result.shop_location = locEl.innerText.trim();

                    // Check official shop
                    if (allText.includes('Official Shop') || allText.includes('Mall')) {
                        result.is_official = true;
                    }

                    // Description
                    if (!result.description) {
                        const descEl = document.querySelector('[class*="description"], [class*="product-detail"]');
                        if (descEl) result.description = descEl.innerText.trim().substring(0, 2000);
                    }

                    return JSON.stringify(result);
                })()
            """)

            # Parse JSON result
            if isinstance(raw_data, str):
                try:
                    raw_data = json.loads(raw_data)
                except json.JSONDecodeError:
                    raw_data = {}

            if not raw_data:
                return {}

            # Build product dict compatible with transform_product
            product = {
                "item_id": item_id,
                "shop_id": shop_id,
                "name": raw_data.get("name", ""),
                "description": raw_data.get("description", ""),
                "price": raw_data.get("price", 0),
                "stock": raw_data.get("stock", 0),
                "sold": raw_data.get("sold", 0),
                "rating": raw_data.get("rating", 0),
                "rating_count": raw_data.get("rating_count", 0),
                "rating_breakdown": [],
                "images": raw_data.get("images", []),
                "variations": [],
                "variants": [],
                "category_id": 0,
                "category_path": raw_data.get("category_path", []),
                "attributes": raw_data.get("attributes", []),
                "condition": "new",
                "shop": {
                    "shop_id": shop_id,
                    "name": raw_data.get("shop_name", ""),
                    "username": "",
                    "location": raw_data.get("shop_location", ""),
                    "is_official": raw_data.get("is_official", False),
                    "is_preferred_plus": False,
                },
                "url": f"{BASE_URL}/product/{shop_id}/{item_id}",
            }

            logger.info(
                "Product extracted via DOM",
                item_id=item_id,
                name=product["name"][:30] if product["name"] else "",
            )
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
