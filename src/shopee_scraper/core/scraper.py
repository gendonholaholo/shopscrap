"""Main Shopee scraper orchestrator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shopee_scraper.core.browser import BrowserManager
from shopee_scraper.core.session import SessionManager
from shopee_scraper.extractors.product import ProductExtractor
from shopee_scraper.extractors.review import ReviewExtractor
from shopee_scraper.extractors.search import SearchExtractor
from shopee_scraper.models.output import ProductOutput
from shopee_scraper.storage.json_storage import JsonStorage
from shopee_scraper.utils.captcha_solver import create_captcha_solver
from shopee_scraper.utils.logging import get_logger
from shopee_scraper.utils.proxy import ProxyPool, load_proxies_from_env
from shopee_scraper.utils.transformer import create_export, transform_product


logger = get_logger(__name__)


class ShopeeScraper:
    """
    Main scraper class for Shopee.

    Orchestrates all scraping operations:
    - Search products by keyword
    - Get product details
    - Get product reviews
    - Manage sessions and authentication
    """

    def __init__(
        self,
        headless: bool = True,
        proxy_pool: ProxyPool | None = None,
        output_dir: str = "./data/output",
        session_dir: str = "./data/sessions",
        session_name: str = "default",
        use_anticaptcha: bool = False,
        twocaptcha_api_key: str | None = None,
    ) -> None:
        """
        Initialize Shopee scraper.

        Args:
            headless: Run browser in headless mode
            proxy_pool: Pool of proxies for rotation
            output_dir: Directory for output files
            session_dir: Directory for session files
            session_name: Session name to auto-restore
            use_anticaptcha: Enable 2Captcha auto-solving
            twocaptcha_api_key: 2Captcha API key (or use env TWOCAPTCHA_API_KEY)
        """
        self.headless = headless
        self.proxy_pool = proxy_pool or load_proxies_from_env()
        self.output_dir = Path(output_dir)
        self.session_dir = Path(session_dir)
        self.session_name = session_name
        self.use_anticaptcha = use_anticaptcha

        # Initialize CAPTCHA solver if enabled
        captcha_solver = None
        if use_anticaptcha:
            captcha_solver = create_captcha_solver(
                api_key=twocaptcha_api_key,
                enabled=True,
            )

        # Initialize components
        self.browser = BrowserManager(
            headless=headless,
            proxy_pool=self.proxy_pool,
        )
        self.session = SessionManager(
            session_dir=str(self.session_dir),
            captcha_solver=captcha_solver,
            use_anticaptcha=use_anticaptcha,
        )
        self.storage = JsonStorage(output_dir=str(self.output_dir))

        # Extractors (initialized after browser starts)
        self._search_extractor: SearchExtractor | None = None
        self._product_extractor: ProductExtractor | None = None
        self._review_extractor: ReviewExtractor | None = None

        self._is_started = False

    async def start(self) -> None:
        """Start the scraper."""
        if self._is_started:
            return

        logger.info("Starting Shopee scraper")
        await self.browser.start()

        # Initialize extractors
        self._search_extractor = SearchExtractor(self.browser)
        self._product_extractor = ProductExtractor(self.browser)
        self._review_extractor = ReviewExtractor(self.browser)

        # Try to restore saved session
        await self._try_restore_session()

        self._is_started = True
        logger.info("Scraper started successfully")

    async def _try_restore_session(self) -> bool:
        """Try to restore saved session cookies."""
        try:
            restored = await self.session.restore_session(
                self.browser,
                self.session_name,
            )
            if restored:
                logger.info("Session restored from saved cookies")
            return restored
        except Exception as e:
            logger.warning(f"Failed to restore session: {e}")
            return False

    async def stop(self) -> None:
        """Stop the scraper and cleanup."""
        if not self._is_started:
            return

        logger.info("Stopping scraper")
        await self.browser.close()
        self._is_started = False
        logger.info("Scraper stopped")

    async def login(
        self,
        username: str,
        password: str,
        session_name: str = "default",
    ) -> bool:
        """
        Login to Shopee.

        Args:
            username: Shopee username/email/phone
            password: Account password
            session_name: Session name for persistence

        Returns:
            True if login successful
        """
        await self._ensure_started()
        return await self.session.ensure_logged_in(
            self.browser,
            username,
            password,
            session_name,
        )

    # =========================================================================
    # Search Operations
    # =========================================================================

    async def search(
        self,
        keyword: str,
        max_pages: int = 1,
        sort_by: str = "relevancy",
        save: bool = True,
        max_reviews: int = 5,
    ) -> list[ProductOutput]:
        """
        Search products by keyword with full details and reviews.

        Automatically fetches product details and reviews for each search result.

        Args:
            keyword: Search keyword
            max_pages: Maximum pages to scrape
            sort_by: Sort order (relevancy, sales, price_asc, price_desc)
            save: Save results to file
            max_reviews: Maximum reviews to fetch per product

        Returns:
            List of ProductOutput instances
        """
        await self._ensure_started()
        assert self._search_extractor is not None
        assert self._product_extractor is not None
        assert self._review_extractor is not None

        logger.info(f"Searching for: {keyword}")

        # Get search results (basic info: item_id, shop_id)
        search_results = await self._search_extractor.search(
            keyword=keyword,
            max_pages=max_pages,
            sort_by=sort_by,
        )

        logger.info(f"Found {len(search_results)} items, fetching details...")

        # Fetch full details and reviews for each product
        products: list[ProductOutput] = []
        for idx, item in enumerate(search_results):
            shop_id = item.get("shop_id")
            item_id = item.get("item_id")

            if not shop_id or not item_id:
                continue

            logger.info(
                f"Fetching details [{idx + 1}/{len(search_results)}]: {item_id}"
            )

            try:
                # Get product details
                product_data = await self._product_extractor.get_product(
                    shop_id=shop_id,
                    item_id=item_id,
                )

                if not product_data:
                    logger.warning(f"No product data for {item_id}")
                    continue

                # Get reviews
                reviews_data: list[dict[str, Any]] = []
                if max_reviews > 0:
                    try:
                        reviews_data = await self._review_extractor.get_reviews(
                            shop_id=shop_id,
                            item_id=item_id,
                            max_reviews=max_reviews,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to get reviews for {item_id}: {e}")

                # Transform to output format
                product_output = transform_product(product_data, reviews_data)
                products.append(product_output)

                # Rate limiting between requests
                await self.browser.random_delay(2.0, 4.0)

            except Exception as e:
                logger.error(f"Failed to get product {item_id}: {e}")

        logger.info(f"Completed: {len(products)}/{len(search_results)} products")

        if save and products:
            export = create_export(products)
            filename = f"search_{self._sanitize_filename(keyword)}"
            path = await self.storage.save(export, filename)
            logger.info(f"Results saved to: {path}")

        return products

    # =========================================================================
    # Product Operations
    # =========================================================================

    async def get_product(
        self,
        shop_id: int,
        item_id: int,
        save: bool = True,
        max_reviews: int = 5,
    ) -> ProductOutput | dict[str, Any]:
        """
        Get product detail with reviews.

        Args:
            shop_id: Shop ID
            item_id: Item ID
            save: Save result to file
            max_reviews: Maximum reviews to fetch

        Returns:
            ProductOutput instance
        """
        await self._ensure_started()
        assert self._product_extractor is not None
        assert self._review_extractor is not None

        product_data = await self._product_extractor.get_product(
            shop_id=shop_id,
            item_id=item_id,
        )

        if not product_data:
            return {}

        # Get reviews
        reviews_data: list[dict[str, Any]] = []
        if max_reviews > 0:
            try:
                reviews_data = await self._review_extractor.get_reviews(
                    shop_id=shop_id,
                    item_id=item_id,
                    max_reviews=max_reviews,
                )
            except Exception as e:
                logger.warning(f"Failed to get reviews for {item_id}: {e}")

        # Transform to output format
        product = transform_product(product_data, reviews_data)

        if save:
            export = create_export([product])
            filename = f"product_{shop_id}_{item_id}"
            path = await self.storage.save(export, filename)
            logger.info(f"Product saved to: {path}")

        return product

    # =========================================================================
    # Review Operations
    # =========================================================================

    async def get_reviews(
        self,
        shop_id: int,
        item_id: int,
        max_reviews: int = 100,
        save: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Get product reviews.

        Args:
            shop_id: Shop ID
            item_id: Item ID
            max_reviews: Maximum reviews to fetch
            save: Save results to file

        Returns:
            List of review dictionaries
        """
        await self._ensure_started()
        assert self._review_extractor is not None

        reviews = await self._review_extractor.get_reviews(
            shop_id=shop_id,
            item_id=item_id,
            max_reviews=max_reviews,
        )

        if save and reviews:
            filename = f"reviews_{shop_id}_{item_id}"
            path = await self.storage.save(reviews, filename)
            logger.info(f"Reviews saved to: {path}")

        return reviews

    async def get_review_summary(
        self,
        shop_id: int,
        item_id: int,
    ) -> dict[str, Any]:
        """
        Get review summary for a product.

        Args:
            shop_id: Shop ID
            item_id: Item ID

        Returns:
            Review summary dictionary
        """
        await self._ensure_started()
        assert self._review_extractor is not None

        return await self._review_extractor.get_reviews_summary(
            shop_id=shop_id,
            item_id=item_id,
        )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _ensure_started(self) -> None:
        """Ensure scraper is started."""
        if not self._is_started:
            await self.start()

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize string for use as filename."""
        import re

        # Remove invalid characters
        sanitized = re.sub(r'[<>:"/\\|?*]', "", name)
        # Replace spaces with underscores
        sanitized = sanitized.replace(" ", "_")
        # Limit length
        return sanitized[:50]

    # =========================================================================
    # Context Manager
    # =========================================================================

    async def __aenter__(self) -> ShopeeScraper:
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        """Async context manager exit."""
        await self.stop()
