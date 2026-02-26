"""Scrape logger: persists normalized product data to PostgreSQL."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from shopee_scraper.storage.database import get_session
from shopee_scraper.storage.models import ScrapeProduct
from shopee_scraper.utils.logging import get_logger


logger = get_logger(__name__)


class ScrapeLogger:
    """Logs scraped product data to PostgreSQL for analytics and debugging."""

    async def log_product(
        self,
        normalized_data: dict[str, Any],
        source: str,
        api_format: str,
        raw_keys: list[str] | None = None,
        job_id: str | None = None,
    ) -> None:
        """Log a single normalized product to the database."""
        shop = normalized_data.get("shop", {})
        try:
            async with get_session() as session:
                record = ScrapeProduct(
                    item_id=normalized_data.get("item_id", 0),
                    shop_id=normalized_data.get("shop_id", 0),
                    name=normalized_data.get("name", ""),
                    description=normalized_data.get("description", ""),
                    price=normalized_data.get("price", 0.0),
                    price_min=normalized_data.get("price_min", 0.0),
                    price_max=normalized_data.get("price_max", 0.0),
                    price_before_discount=normalized_data.get(
                        "price_before_discount", 0.0
                    ),
                    stock=normalized_data.get("stock", 0),
                    sold=normalized_data.get("sold", 0),
                    rating=normalized_data.get("rating", 0.0),
                    rating_count=normalized_data.get("rating_count", 0),
                    images=normalized_data.get("images", []),
                    variants=normalized_data.get("variants", []),
                    variations=normalized_data.get("variations", []),
                    category_id=normalized_data.get("category_id", 0),
                    category_path=normalized_data.get("category_path", []),
                    condition=normalized_data.get("condition", "new"),
                    shop_name=shop.get("name", "") if isinstance(shop, dict) else "",
                    shop_username=(
                        shop.get("username", "") if isinstance(shop, dict) else ""
                    ),
                    shop_location=(
                        shop.get("location", "") if isinstance(shop, dict) else ""
                    ),
                    shop_rating=(
                        shop.get("rating", 0.0) if isinstance(shop, dict) else 0.0
                    ),
                    shop_is_official=(
                        shop.get("is_official", False)
                        if isinstance(shop, dict)
                        else False
                    ),
                    attributes=normalized_data.get("attributes", []),
                    url=normalized_data.get("url", ""),
                    source=source,
                    api_format=api_format,
                    raw_top_keys=raw_keys,
                    job_id=job_id,
                    scraped_at=datetime.now(timezone.utc),
                )
                session.add(record)

            logger.debug(
                "Logged product to DB",
                item_id=normalized_data.get("item_id"),
                source=source,
            )
        except Exception as e:
            logger.warning(f"Failed to log product to DB: {e}")

    async def log_products(
        self,
        products: list[dict[str, Any]],
        source: str,
        api_format: str,
        job_id: str | None = None,
    ) -> None:
        """Log multiple products in batch."""
        for product in products:
            await self.log_product(
                normalized_data=product,
                source=source,
                api_format=api_format,
                job_id=job_id,
            )
