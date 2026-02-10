"""Scraper service - shared business logic for API and gRPC."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from shopee_scraper.core.scraper import ShopeeScraper
from shopee_scraper.extension.bridge import ExtensionBridge
from shopee_scraper.extension.protocol import TaskType
from shopee_scraper.models.output import ProductOutput, _dataclass_to_dict
from shopee_scraper.utils.config import get_settings
from shopee_scraper.utils.health_checker import HealthChecker
from shopee_scraper.utils.logging import get_logger
from shopee_scraper.utils.proxy import ProxyConfig, ProxyPool
from shopee_scraper.utils.system_monitor import get_uptime
from shopee_scraper.utils.transformer import create_export


if TYPE_CHECKING:
    from shopee_scraper.extension.manager import ExtensionManager
    from shopee_scraper.services.cache import ProductCache, ReviewCache

logger = get_logger(__name__)


class ScraperService:
    """
    Service layer that wraps ShopeeScraper for use by API/gRPC.

    This provides a clean interface for external communication layers
    while keeping business logic centralized.

    Supports optional caching via ProductCache and ReviewCache for
    improved performance and reduced scraping load.

    Supports Chrome Extension as an alternative execution backend
    (extension mode) for bypassing anti-bot detection.
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
        self._product_cache: ProductCache | None = None
        self._review_cache: ReviewCache | None = None
        self._extension_manager: ExtensionManager | None = None
        self._extension_bridge = ExtensionBridge()

    def set_caches(
        self,
        product_cache: ProductCache | None = None,
        review_cache: ReviewCache | None = None,
    ) -> None:
        """
        Set cache instances for the service.

        Args:
            product_cache: Optional ProductCache for caching product data
            review_cache: Optional ReviewCache for caching review data
        """
        self._product_cache = product_cache
        self._review_cache = review_cache
        if product_cache:
            logger.info("Product caching enabled")
        if review_cache:
            logger.info("Review caching enabled")

    def set_extension_manager(self, manager: ExtensionManager) -> None:
        """Set the ExtensionManager for extension-based scraping."""
        self._extension_manager = manager
        logger.info("Extension manager set on ScraperService")

    def _should_use_extension(self, execution_mode: str) -> bool:
        """Determine whether to use extension for this request."""
        if execution_mode == "extension":
            return True
        if execution_mode == "browser":
            return False
        # auto mode: prefer extension if available
        return (
            self._extension_manager is not None
            and self._extension_manager.has_available()
        )

    async def _get_scraper(self) -> ShopeeScraper:
        """Get or create scraper instance with proxy and captcha settings."""
        if self._scraper is None:
            settings = get_settings()

            # Setup proxy pool if enabled
            proxy_pool = None
            if settings.proxy.enabled and settings.proxy.host:
                proxy_config = ProxyConfig(
                    host=settings.proxy.host,
                    port=settings.proxy.port,
                    username=settings.proxy.username,
                    password=settings.proxy.password,
                )
                proxy_pool = ProxyPool([proxy_config])
                logger.info(
                    "Proxy enabled",
                    host=settings.proxy.host,
                    port=settings.proxy.port,
                )

            # Setup captcha solver if enabled
            use_anticaptcha = settings.captcha.enabled
            captcha_api_key = settings.captcha.api_key if use_anticaptcha else None
            if use_anticaptcha:
                logger.info(
                    "CAPTCHA auto-solver enabled", provider=settings.captcha.provider
                )

            self._scraper = ShopeeScraper(
                headless=self._headless,
                proxy_pool=proxy_pool,
                output_dir=self._output_dir,
                use_anticaptcha=use_anticaptcha,
                twocaptcha_api_key=captcha_api_key,
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
        execution_mode: str = "auto",
    ) -> dict[str, Any]:
        """
        Search products by keyword with full details.

        Args:
            execution_mode: "auto" | "browser" | "extension"

        Returns:
            Dict with ExportOutput-compatible format
        """
        if self._should_use_extension(execution_mode):
            return await self._search_via_extension(
                keyword=keyword,
                max_pages=max_pages,
                sort_by=sort_by,
            )

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
        use_cache: bool = True,
        execution_mode: str = "auto",
    ) -> dict[str, Any] | None:
        """
        Get product detail by shop_id and item_id.

        Args:
            shop_id: Shopee shop ID
            item_id: Shopee item ID
            max_reviews: Maximum reviews to fetch
            save: Whether to save to file
            use_cache: Whether to use cache (if available)
            execution_mode: "auto" | "browser" | "extension"

        Returns:
            Product data dict or None if not found
        """
        # Try cache first if enabled
        if use_cache and self._product_cache:
            cached = await self._product_cache.get(shop_id, item_id)
            if cached:
                logger.info(f"Service: cache hit for product {shop_id}/{item_id}")
                return cached

        if self._should_use_extension(execution_mode):
            result = await self._get_product_via_extension(
                shop_id=shop_id, item_id=item_id
            )
            if use_cache and self._product_cache and result:
                await self._product_cache.set(shop_id, item_id, result)
            return result

        # Fetch from scraper
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

        # Convert to dict
        if isinstance(product, ProductOutput):
            result = _dataclass_to_dict(product)
        else:
            result = product

        # Cache the result if caching enabled
        if use_cache and self._product_cache and result:
            await self._product_cache.set(shop_id, item_id, result)

        return result

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
        execution_mode: str = "auto",
    ) -> dict[str, Any]:
        """Get product reviews."""
        if self._should_use_extension(execution_mode):
            return await self._get_reviews_via_extension(
                shop_id=shop_id,
                item_id=item_id,
                max_reviews=max_reviews,
            )

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
    # Extension-based Operations
    # =========================================================================

    async def _search_via_extension(
        self,
        keyword: str,
        max_pages: int = 1,
        sort_by: str = "relevancy",
    ) -> dict[str, Any]:
        """Execute search via Chrome Extension."""
        assert self._extension_manager is not None
        logger.info(f"Service: searching via extension for '{keyword}'")

        task_id = await self._extension_manager.dispatch_task(
            task_type=TaskType.SEARCH,
            params={
                "keyword": keyword,
                "maxPages": max_pages,
                "sortBy": sort_by,
            },
        )

        raw_data = await self._extension_manager.wait_for_result(task_id)
        products = self._extension_bridge.process_search_result(raw_data)
        return self._extension_bridge.create_export_output(products)

    async def _get_product_via_extension(
        self,
        shop_id: int,
        item_id: int,
    ) -> dict[str, Any] | None:
        """Get product detail via Chrome Extension."""
        assert self._extension_manager is not None
        logger.info(f"Service: getting product via extension {shop_id}/{item_id}")

        task_id = await self._extension_manager.dispatch_task(
            task_type=TaskType.PRODUCT,
            params={"shopId": shop_id, "itemId": item_id},
        )

        raw_data = await self._extension_manager.wait_for_result(task_id)
        product = self._extension_bridge.process_product_result(raw_data)
        if not product:
            return None
        return _dataclass_to_dict(product)

    async def _get_reviews_via_extension(
        self,
        shop_id: int,
        item_id: int,
        max_reviews: int = 100,
    ) -> dict[str, Any]:
        """Get reviews via Chrome Extension."""
        assert self._extension_manager is not None
        logger.info(f"Service: getting reviews via extension {shop_id}/{item_id}")

        task_id = await self._extension_manager.dispatch_task(
            task_type=TaskType.REVIEWS,
            params={
                "shopId": shop_id,
                "itemId": item_id,
                "maxReviews": max_reviews,
            },
        )

        raw_data = await self._extension_manager.wait_for_result(task_id)
        reviews = self._extension_bridge.process_reviews_result(raw_data)
        return {
            "shop_id": shop_id,
            "item_id": item_id,
            "total_count": len(reviews),
            "reviews": reviews,
        }

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
