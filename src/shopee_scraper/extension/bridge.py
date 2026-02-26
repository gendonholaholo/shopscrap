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

    def normalize_product_result(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """Normalize raw product API data without transforming to ProductOutput.

        Useful for getting the intermediate dict representation for DB logging
        or further processing.

        Args:
            raw_data: Raw JSON from /api/v4/pdp/get_pc or /api/v4/item/get

        Returns:
            Normalized product dict (same format as extractor parse output)
        """
        data = raw_data.get("data", raw_data)
        return self._normalize_product(data)

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

        # Price conversion (guard against None values from API)
        price_raw = item.get("price") or 0
        price_min = item.get("price_min") or price_raw
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
            "stock": item.get("stock") or 0,
            "sold": item.get("sold") or item.get("historical_sold") or 0,
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

    def _normalize_product(self, data: dict[str, Any]) -> dict[str, Any]:  # noqa: PLR0915
        """Normalize product detail API response.

        Handles both the legacy /api/v4/item/get format (itemid, name, price)
        and the new BFF /api/v4/pdp/get_pc format (item_id, title, product_price).
        """
        item = data.get("item", data)

        item_id = item.get("itemid", item.get("item_id", 0))
        shop_id = item.get("shopid", item.get("shop_id", 0))

        if not item_id:
            return {}

        # --- Detect format: new BFF has product_price sub-object ---
        product_price = data.get("product_price", {})
        if product_price:
            # New BFF format (/api/v4/pdp/get_pc)
            price_obj = product_price.get("price", {})
            single_val = price_obj.get("single_value", -1)
            range_min = price_obj.get("range_min") or 0
            range_max = price_obj.get("range_max") or range_min
            price_raw = single_val if (single_val and single_val != -1) else range_min
            price = (price_raw or 0) / PRICE_DIVISOR
            price_max_val = (range_max or price_raw) / PRICE_DIVISOR

            pbd_obj = product_price.get("price_before_discount", {})
            pbd_single = pbd_obj.get("single_value", -1) if pbd_obj else -1
            pbd_min = pbd_obj.get("range_min") or 0 if pbd_obj else 0
            price_before_discount = (
                (pbd_single if (pbd_single and pbd_single != -1) else pbd_min)
                / PRICE_DIVISOR
                if pbd_obj
                else 0
            )

            # Images from product_images sub-object
            pi = data.get("product_images", {})
            raw_images = pi.get("images", []) if isinstance(pi, dict) else []

            # Shop from shop_detailed
            shop_info = data.get("shop_detailed", {})

            # Ratings/reviews from product_review
            pr = data.get("product_review", {})
            rating = pr.get("rating_star") or item.get("item_rating", {}).get(
                "rating_star", 0
            )
            rating_count = pr.get("total_rating_count") or pr.get("cmt_count") or 0
            rating_breakdown = pr.get("rating_count", [])
            sold = pr.get("historical_sold") or 0

            # Stock: may be hidden in BFF; use is_hide_stock flag
            stock_val = item.get("stock") or item.get("normal_stock")
            if stock_val is None:
                # Stock is hidden — use availability indicator
                is_available_str = item.get("stock_display", "")
                stock_val = (
                    1 if is_available_str and is_available_str not in ("", "0") else 0
                )

            # Name from title field
            name = item.get("title") or item.get("name", "")

            # Description: BFF puts it under product_detail
            product_detail = data.get("product_detail", {})
            description = (
                (
                    product_detail.get("description", "")
                    if isinstance(product_detail, dict)
                    else ""
                )
                or item.get("description")
                or ""
            )

            if not description:
                logger.debug(
                    "BFF format yielded empty description",
                    item_id=item_id,
                    top_keys=list(data.keys()),
                )
        else:
            # Legacy format (/api/v4/item/get)
            price_raw = item.get("price", 0)
            price_min = item.get("price_min", price_raw)
            price_max = item.get("price_max", price_raw)
            price = (price_min or 0) / PRICE_DIVISOR
            price_max_val = (price_max or 0) / PRICE_DIVISOR if price_max else price
            price_before_discount = (
                item.get("price_before_discount") or 0
            ) / PRICE_DIVISOR

            raw_images = item.get("images", [])
            shop_info = data.get("shop_info", {})

            item_rating = item.get("item_rating", {})
            rating = item_rating.get("rating_star", 0)
            rating_count = item.get("cmt_count", 0) or 0
            rating_breakdown = item_rating.get("rating_count", [])
            sold = item.get("sold") or item.get("historical_sold") or 0
            stock_val = item.get("stock") or 0

            name = item.get("name") or item.get("title", "")
            description = item.get("description", "")

        # Images — handle both string hashes and dict objects
        image_urls: list[str] = []
        for img in raw_images:
            if isinstance(img, str):
                image_urls.append(f"https://cf.shopee.co.id/file/{img}")
            elif isinstance(img, dict):
                img_hash = (
                    img.get("image_url") or img.get("url") or img.get("img") or ""
                )
                if img_hash:
                    image_urls.append(
                        img_hash
                        if img_hash.startswith("http")
                        else f"https://cf.shopee.co.id/file/{img_hash}"
                    )

        # Variants/Models (same structure in both formats)
        models = item.get("models", [])
        variants = []
        for model in models:
            model_price = (model.get("price") or 0) / PRICE_DIVISOR
            model_stock = model.get("stock") or 0
            variants.append(
                {
                    "model_id": model.get("modelid") or model.get("model_id") or 0,
                    "name": model.get("name", ""),
                    "price": model_price,
                    "stock": model_stock,
                    "sold": model.get("sold") or 0,
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

        # Shop info (works for both shop_detailed and shop_info formats)
        shop_account = (
            shop_info.get("account", {}) if isinstance(shop_info, dict) else {}
        )
        shop_username = shop_account.get("username", "") if shop_account else ""

        return {
            "item_id": item_id,
            "shop_id": shop_id,
            "name": name,
            "description": description,
            "price": price,
            "price_min": price,
            "price_max": price_max_val,
            "price_before_discount": price_before_discount,
            "stock": stock_val,
            "sold": sold,
            "rating": rating,
            "rating_count": rating_count,
            "rating_breakdown": rating_breakdown,
            "images": image_urls,
            "variants": variants,
            "variations": variations,
            "category_id": item.get("catid") or item.get("cat_id", 0),
            "category_path": category_path,
            "condition": "new" if item.get("condition", 1) == 1 else "used",
            "shop": {
                "shop_id": shop_id,
                "name": shop_info.get("name", "")
                if isinstance(shop_info, dict)
                else "",
                "username": shop_username,
                "location": shop_info.get("shop_location", "")
                if isinstance(shop_info, dict)
                else "",
                "rating": shop_info.get("rating_star", 0)
                if isinstance(shop_info, dict)
                else 0,
                "is_official": shop_info.get("is_official_shop", False)
                if isinstance(shop_info, dict)
                else False,
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
