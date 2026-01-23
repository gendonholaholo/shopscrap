"""Scraper service - shared business logic for API and gRPC."""

from __future__ import annotations

from typing import Any

from shopee_scraper.core.scraper import ShopeeScraper
from shopee_scraper.models.output import ProductOutput, _dataclass_to_dict
from shopee_scraper.utils.health_checker import HealthChecker
from shopee_scraper.utils.logging import get_logger
from shopee_scraper.utils.system_monitor import get_uptime
from shopee_scraper.utils.transformer import create_export


logger = get_logger(__name__)


class ScraperService:
    """
    Service layer that wraps ShopeeScraper for use by API/gRPC.

    This provides a clean interface for external communication layers
    while keeping business logic centralized.
    """

    def __init__(
        self,
        headless: bool = True,
        output_dir: str = "./data/output",
    ) -> None:
        """Initialize scraper service."""
        self._headless = headless
        self._output_dir = output_dir
        self._scraper: ShopeeScraper | None = None
        self._health_checker = HealthChecker(data_dir="./data")

    async def _get_scraper(self) -> ShopeeScraper:
        """Get or create scraper instance."""
        if self._scraper is None:
            self._scraper = ShopeeScraper(
                headless=self._headless,
                output_dir=self._output_dir,
            )
            await self._scraper.start()
        return self._scraper

    async def close(self) -> None:
        """Close scraper connection."""
        if self._scraper:
            await self._scraper.stop()
            self._scraper = None

    # =========================================================================
    # Search Operations
    # =========================================================================

    async def search_products(
        self,
        keyword: str,
        max_pages: int = 1,
        sort_by: str = "relevancy",
        max_reviews: int = 5,
        save: bool = False,
    ) -> dict[str, Any]:
        """
        Search products by keyword with full details.

        Returns:
            Dict with ExportOutput-compatible format
        """
        scraper = await self._get_scraper()
        logger.info(f"Service: searching for '{keyword}'")

        # ShopeeScraper.search now returns list[ProductOutput]
        products: list[ProductOutput] = await scraper.search(
            keyword=keyword,
            max_pages=max_pages,
            sort_by=sort_by,
            max_reviews=max_reviews,
            save=save,
        )

        # Create ExportOutput wrapper
        export = create_export(products)

        return _dataclass_to_dict(export)

    # =========================================================================
    # Product Operations
    # =========================================================================

    async def get_product(
        self,
        shop_id: int,
        item_id: int,
        max_reviews: int = 5,
        save: bool = False,
    ) -> dict[str, Any] | None:
        """Get product detail by shop_id and item_id."""
        scraper = await self._get_scraper()
        logger.info(f"Service: getting product {shop_id}/{item_id}")

        product = await scraper.get_product(
            shop_id=shop_id,
            item_id=item_id,
            max_reviews=max_reviews,
            save=save,
        )

        if not product:
            return None

        # If it's a ProductOutput, convert to dict
        if isinstance(product, ProductOutput):
            return _dataclass_to_dict(product)

        return product

    async def get_products_batch(
        self,
        keyword: str,
        max_products: int = 10,
        max_reviews: int = 5,
        save: bool = False,
    ) -> dict[str, Any]:
        """
        Search and get full details for products.

        This is a convenience method that limits the number of products
        to fetch details for (useful for API with limits).
        """
        scraper = await self._get_scraper()
        logger.info(
            f"Service: batch get products for '{keyword}' (max: {max_products})"
        )

        # Use search which now fetches full details automatically
        # We limit via search extractor results
        products: list[ProductOutput] = await scraper.search(
            keyword=keyword,
            max_pages=1,  # Single page for batch
            max_reviews=max_reviews,
            save=save,
        )

        # Limit to max_products
        products = products[:max_products]

        # Create ExportOutput wrapper
        export = create_export(products)

        return _dataclass_to_dict(export)

    # =========================================================================
    # Review Operations
    # =========================================================================

    async def get_reviews(
        self,
        shop_id: int,
        item_id: int,
        max_reviews: int = 100,
        save: bool = False,
    ) -> dict[str, Any]:
        """Get product reviews."""
        scraper = await self._get_scraper()
        logger.info(f"Service: getting reviews for {shop_id}/{item_id}")

        reviews = await scraper.get_reviews(
            shop_id=shop_id,
            item_id=item_id,
            max_reviews=max_reviews,
            save=save,
        )

        return {
            "shop_id": shop_id,
            "item_id": item_id,
            "total_count": len(reviews),
            "reviews": reviews,
        }

    async def get_review_summary(
        self,
        shop_id: int,
        item_id: int,
    ) -> dict[str, Any]:
        """Get review summary for a product."""
        scraper = await self._get_scraper()
        logger.info(f"Service: getting review summary for {shop_id}/{item_id}")

        summary = await scraper.get_review_summary(
            shop_id=shop_id,
            item_id=item_id,
        )

        return summary

    # =========================================================================
    # Health Check
    # =========================================================================

    async def health_check(self) -> dict[str, Any]:
        """
        Comprehensive health check.

        Returns:
            Dict with health status and component details
        """
        # Run health checks
        health_result = await self._health_checker.check_health()

        # Convert components to dict
        components = [
            {
                "name": c.name,
                "status": c.status,
                "message": c.message,
                "latency_ms": c.latency_ms,
            }
            for c in health_result.components
        ]

        # Check browser availability from components
        browser_check = next(
            (c for c in health_result.components if c.name == "browser"),
            None,
        )
        browser_available = (
            browser_check.status == "healthy" if browser_check else False
        )

        return {
            "status": health_result.status,
            "scraper_initialized": self._scraper is not None,
            "browser_available": browser_available,
            "uptime_seconds": get_uptime(),
            "timestamp": health_result.timestamp.isoformat(),
            "components": components,
            "total_checks": health_result.total_checks,
            "healthy_checks": health_result.healthy_checks,
            "degraded_checks": health_result.degraded_checks,
            "unhealthy_checks": health_result.unhealthy_checks,
        }

    async def liveness_check(self) -> dict[str, Any]:
        """
        Simple liveness check - is the service alive?

        Returns:
            Basic alive status
        """
        from datetime import datetime

        return {
            "status": "alive",
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def readiness_check(self) -> dict[str, Any]:
        """
        Readiness check - is the service ready to accept requests?

        Returns:
            Readiness status with critical component checks
        """
        from datetime import datetime

        # Run critical checks only
        health_result = await self._health_checker.check_health()

        # Service is ready if no unhealthy components
        ready = health_result.unhealthy_checks == 0

        components = [
            {
                "name": c.name,
                "status": c.status,
                "message": c.message,
            }
            for c in health_result.components
        ]

        return {
            "status": "ready" if ready else "not_ready",
            "ready": ready,
            "timestamp": datetime.utcnow().isoformat(),
            "checks": components,
        }
