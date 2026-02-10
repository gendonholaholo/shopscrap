"""Extension bridge: transforms raw Shopee API JSON from extension into output models.

Reuses existing transformer pipeline — the bridge normalizes raw API JSON into
the same dict format that extractors produce, then calls transform_product().
"""

from __future__ import annotations

from typing import Any

from shopee_scraper.models.output import ProductOutput
from shopee_scraper.utils.constants import BASE_URL, PRICE_DIVISOR
from shopee_scraper.utils.logging import get_logger
from shopee_scraper.utils.transformer import create_export, transform_product


logger = get_logger(__name__)


class ExtensionBridge:
    """Transforms raw Shopee API JSON from the Chrome Extension into ProductOutput.

    The extension captures raw Shopee internal API responses. This bridge normalizes
    them into the same dict format that SearchExtractor.parse() and
    ProductExtractor.parse() produce, then feeds them through the existing
    transform_product() pipeline.
    """

    def process_search_result(self, raw_data: dict[str, Any]) -> list[ProductOutput]:
        """Process raw search API response into ProductOutput list.

        Args:
            raw_data: Raw JSON from /api/v4/search/search_items

        Returns:
            List of ProductOutput
        """
        items = raw_data.get("items", [])
        if not items:
            items = raw_data.get("data", {}).get("items", [])

        products: list[ProductOutput] = []
        for item in items:
            item_basic = item.get("item_basic", item)
            normalized = self._normalize_search_item(item_basic)
            if normalized:
                products.append(transform_product(normalized))

        logger.info(f"Bridge: processed {len(products)} search results")
        return products

    def process_product_result(self, raw_data: dict[str, Any]) -> ProductOutput | None:
        """Process raw product API response into ProductOutput.

        Args:
            raw_data: Raw JSON from /api/v4/pdp/get_pc or /api/v4/item/get

        Returns:
            ProductOutput or None if parsing fails
        """
        # pdp/get_pc wraps data differently
        data = raw_data.get("data", raw_data)
        normalized = self._normalize_product(data)
        if not normalized:
            return None

        return transform_product(normalized)

    def process_reviews_result(self, raw_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Process raw reviews API response.

        Args:
            raw_data: Raw JSON from /api/v2/item/get_ratings

        Returns:
            List of normalized review dicts
        """
        data = raw_data.get("data", raw_data)
        ratings = data.get("ratings", [])

        reviews: list[dict[str, Any]] = []
        for rating in ratings:
            review = self._normalize_review(rating)
            if review:
                reviews.append(review)

        logger.info(f"Bridge: processed {len(reviews)} reviews")
        return reviews

    def create_export_output(self, products: list[ProductOutput]) -> dict[str, Any]:
        """Wrap products in ExportOutput format."""
        export = create_export(products)
        return export.model_dump()

    # -------------------------------------------------------------------------
    # Normalization: raw API → extractor-compatible dict
    # -------------------------------------------------------------------------

    def _normalize_search_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Normalize a search item into the format transform_product() expects.

        Maps from raw Shopee API fields to the same dict keys that
        SearchExtractor.parse() produces.
        """
        item_id = item.get("itemid", item.get("item_id", 0))
        shop_id = item.get("shopid", item.get("shop_id", 0))

        if not item_id or not shop_id:
            return {}

        # Price conversion
        price_raw = item.get("price", 0)
        price_min = item.get("price_min", price_raw)
        price = price_min / PRICE_DIVISOR if price_min else 0

        # Images
        images = item.get("images", [])
        image_urls = [f"https://cf.shopee.co.id/file/{img}" for img in images]

        # Rating
        item_rating = item.get("item_rating", {})
        rating = item_rating.get("rating_star", 0)
        rating_counts = item_rating.get("rating_count", [0])
        rating_count = sum(rating_counts) if isinstance(rating_counts, list) else 0

        return {
            "item_id": item_id,
            "shop_id": shop_id,
            "name": item.get("name", ""),
            "price": price,
            "stock": item.get("stock", 0),
            "sold": item.get("sold", item.get("historical_sold", 0)),
            "rating": rating,
            "rating_count": rating_count,
            "images": image_urls,
            "url": f"{BASE_URL}/product/{shop_id}/{item_id}",
            "shop": {
                "shop_id": shop_id,
                "name": "",
                "username": "",
                "location": item.get("shop_location", ""),
                "is_official": item.get("is_official_shop", False),
            },
        }

    def _normalize_product(self, data: dict[str, Any]) -> dict[str, Any]:
        """Normalize product detail API response.

        Maps from raw /api/v4/pdp/get_pc response to the same dict keys that
        ProductExtractor.parse() produces.
        """
        item = data.get("item", data)

        item_id = item.get("itemid", item.get("item_id", 0))
        shop_id = item.get("shopid", item.get("shop_id", 0))

        if not item_id:
            return {}

        # Price
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

        # Tier variations
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
        shop_info = data.get("shop_info", {})

        # Rating
        item_rating = item.get("item_rating", {})

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
            "stock": item.get("stock", 0),
            "sold": item.get("sold", item.get("historical_sold", 0)),
            "rating": item_rating.get("rating_star", 0),
            "rating_count": item.get("cmt_count", 0),
            "rating_breakdown": item_rating.get("rating_count", []),
            "images": image_urls,
            "variants": variants,
            "variations": variations,
            "category_id": item.get("catid", 0),
            "category_path": category_path,
            "condition": "new" if item.get("is_new", True) else "used",
            "shop": {
                "shop_id": shop_id,
                "name": shop_info.get("name", ""),
                "username": shop_info.get("account", {}).get("username", ""),
                "location": shop_info.get("shop_location", ""),
                "rating": shop_info.get("rating_star", 0),
                "is_official": shop_info.get("is_official_shop", False),
            },
            "attributes": item.get("attributes", []),
            "url": f"{BASE_URL}/product/{shop_id}/{item_id}",
        }

    def _normalize_review(self, rating: dict[str, Any]) -> dict[str, Any]:
        """Normalize a single review from ratings API."""
        author_username = rating.get("author_username", "")
        author_portrait = rating.get("author_portrait", "")

        images = rating.get("images", [])
        videos = rating.get("videos", [])

        return {
            "rating_id": rating.get("cmtid", ""),
            "rating": rating.get("rating_star", 0),
            "comment": rating.get("comment", ""),
            "images": images,
            "videos": [v.get("url", "") for v in videos] if videos else [],
            "variation": rating.get("product_items", [{}])[0].get("model_name", "")
            if rating.get("product_items")
            else "",
            "likes": rating.get("like_count", 0),
            "created_at": rating.get("ctime", ""),
            "is_anonymous": rating.get("anonymous", False),
            "shop_reply": rating.get("itemrpt", {}).get("cmt", "")
            if rating.get("itemrpt")
            else None,
            "author": {
                "user_id": rating.get("author_shopid", ""),
                "username": author_username,
                "avatar": f"https://cf.shopee.co.id/file/{author_portrait}"
                if author_portrait
                else "",
            },
        }
