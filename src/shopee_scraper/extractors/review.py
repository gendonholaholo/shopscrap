"""Review extractor for Shopee products."""

from __future__ import annotations

import contextlib
from datetime import datetime
from typing import TYPE_CHECKING, Any

from shopee_scraper.extractors.base import BaseExtractor
from shopee_scraper.utils.constants import BASE_URL, REVIEW_API
from shopee_scraper.utils.logging import get_logger


if TYPE_CHECKING:
    from shopee_scraper.core.browser import BrowserManager, Page

# Type alias for nodriver response (placeholder for review extractor refactoring)
Response = object

logger = get_logger(__name__)


class ReviewExtractor(BaseExtractor):
    """
    Extract product reviews from Shopee.

    Uses Shopee's internal API v4:
    - /api/v4/pdp/get_rw - Product reviews with ratings
    """

    # Review filter types
    FILTER_ALL = 0
    FILTER_WITH_COMMENT = 1
    FILTER_WITH_MEDIA = 2

    def __init__(self, browser: BrowserManager) -> None:
        """
        Initialize review extractor.

        Args:
            browser: BrowserManager instance
        """
        self.browser = browser
        self._intercepted_data: list[dict[str, Any]] = []

    async def get_reviews(
        self,
        shop_id: int,
        item_id: int,
        max_reviews: int = 100,
        filter_type: int = 0,
        rating_filter: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Get reviews for a product.

        Args:
            shop_id: Shop ID
            item_id: Item ID
            max_reviews: Maximum number of reviews to fetch
            filter_type: 0=all, 1=with comment, 2=with media
            rating_filter: 0=all, 1-5=specific rating

        Returns:
            List of review dictionaries
        """
        logger.info(
            "Getting reviews",
            shop_id=shop_id,
            item_id=item_id,
            max_reviews=max_reviews,
        )

        all_reviews: list[dict[str, Any]] = []
        page = await self.browser.new_page()
        self._intercepted_data.clear()

        try:
            # Setup response interception
            page.on("response", self._handle_response)

            # Navigate to product page reviews section
            product_url = f"{BASE_URL}/product/{shop_id}/{item_id}"
            await self.browser.goto(page, product_url)

            # Scroll to reviews section
            await self._scroll_to_reviews(page)

            # Click on reviews tab if needed
            await self._click_reviews_tab(page)

            # Wait for reviews to load
            await self.browser.random_delay(1.0, 2.0)

            # Extract reviews with pagination
            offset = 0
            per_page = 6  # Shopee loads 6 reviews at a time

            while len(all_reviews) < max_reviews:
                # Check intercepted data
                if self._intercepted_data:
                    for data in self._intercepted_data:
                        reviews = self._parse_api_response(data)
                        for review in reviews:
                            if review not in all_reviews:
                                all_reviews.append(review)

                    self._intercepted_data.clear()

                    logger.info(f"Collected {len(all_reviews)} reviews so far")

                    if len(all_reviews) >= max_reviews:
                        break

                # Try to load more reviews
                more_loaded = await self._load_more_reviews(page)
                if not more_loaded:
                    logger.info("No more reviews to load")
                    break

                offset += per_page
                await self.browser.random_delay(1.0, 2.0)

            # Trim to max
            all_reviews = all_reviews[:max_reviews]

        finally:
            await self.browser.close_page(page)

        logger.info(f"Review extraction completed: {len(all_reviews)} reviews")
        return all_reviews

    async def get_reviews_summary(
        self,
        shop_id: int,
        item_id: int,
    ) -> dict[str, Any]:
        """
        Get review summary/statistics for a product.

        Args:
            shop_id: Shop ID
            item_id: Item ID

        Returns:
            Review summary dictionary
        """
        logger.info("Getting review summary", shop_id=shop_id, item_id=item_id)

        page = await self.browser.new_page()

        try:
            product_url = f"{BASE_URL}/product/{shop_id}/{item_id}"
            await self.browser.goto(page, product_url)
            await self._scroll_to_reviews(page)
            await self.browser.random_delay(1.0, 2.0)

            # Extract summary from page
            summary = await self._extract_review_summary(page)
            summary["shop_id"] = shop_id
            summary["item_id"] = item_id

            return summary

        finally:
            await self.browser.close_page(page)

    async def _handle_response(self, response: Response) -> None:
        """Handle intercepted API responses."""
        url = response.url

        if REVIEW_API in url and response.status == 200:
            try:
                data = await response.json()
                self._intercepted_data.append(data)
                logger.debug("Intercepted review API response")
            except Exception as e:
                logger.warning(f"Failed to parse review API response: {e}")

    async def _scroll_to_reviews(self, page: Page) -> None:
        """Scroll to the reviews section of the page."""
        try:
            # Find reviews section
            selectors = [
                "[class*='product-rating']",
                "[class*='review']",
                "#review",
            ]

            for selector in selectors:
                element = await page.query_selector(selector)
                if element:
                    await element.scroll_into_view_if_needed()
                    await self.browser.random_delay(0.5, 1.0)
                    return

            # Fallback: scroll down
            await self.browser.scroll_page(page, scroll_count=5)

        except Exception as e:
            logger.warning(f"Failed to scroll to reviews: {e}")

    async def _click_reviews_tab(self, page: Page) -> None:
        """Click on reviews tab if separate from product info."""
        try:
            tab_selectors = [
                "[class*='review-tab']",
                "button:has-text('Ulasan')",
                "[data-tab='reviews']",
            ]

            for selector in tab_selectors:
                tab = await page.query_selector(selector)
                if tab:
                    await tab.click()
                    await self.browser.random_delay(0.5, 1.0)
                    return

        except Exception as e:
            logger.debug(f"No separate reviews tab: {e}")

    async def _load_more_reviews(self, page: Page) -> bool:
        """Click load more button or scroll to load more reviews."""
        try:
            # Try "load more" button
            load_more_selectors = [
                "button:has-text('Lihat Lebih')",
                "button:has-text('Muat Lebih')",
                "[class*='load-more']",
            ]

            for selector in load_more_selectors:
                button = await page.query_selector(selector)
                if button:
                    is_visible = await button.is_visible()
                    if is_visible:
                        await button.click()
                        await self.browser.random_delay(1.0, 2.0)
                        return True

            # Scroll to trigger lazy loading
            await page.evaluate("window.scrollBy(0, 500)")
            await self.browser.random_delay(0.5, 1.0)

            return True

        except Exception as e:
            logger.warning(f"Failed to load more reviews: {e}")
            return False

    async def _extract_review_summary(self, page: Page) -> dict[str, Any]:
        """Extract review summary from DOM."""
        summary = {
            "total_reviews": 0,
            "average_rating": 0.0,
            "rating_breakdown": {},
        }

        try:
            # Get average rating
            rating_el = await page.query_selector("[class*='rating-star'] + span")
            if rating_el:
                rating_text = await rating_el.inner_text()
                with contextlib.suppress(ValueError):
                    summary["average_rating"] = float(rating_text)

            # Get total reviews
            count_el = await page.query_selector("[class*='rating-count']")
            if count_el:
                count_text = await count_el.inner_text()
                import re

                match = re.search(r"(\d+)", count_text.replace(".", ""))
                if match:
                    summary["total_reviews"] = int(match.group(1))

            # Get rating breakdown
            breakdown_els = await page.query_selector_all("[class*='rating-filter']")
            for el in breakdown_els:
                text = await el.inner_text()
                import re

                match = re.search(r"(\d)\s*(?:Bintang|Star)[^\d]*(\d+)", text)
                if match:
                    star = int(match.group(1))
                    count = int(match.group(2).replace(".", ""))
                    summary["rating_breakdown"][star] = count

        except Exception as e:
            logger.warning(f"Failed to extract review summary: {e}")

        return summary

    def _parse_api_response(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Parse API response into review list."""
        reviews = []

        # Get ratings from response
        ratings = data.get("data", {}).get("ratings", [])
        if not ratings:
            ratings = data.get("ratings", [])

        for rating in ratings:
            review = self.parse(rating)
            if review:
                reviews.append(review)

        return reviews

    def parse(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """Parse and structure review data from API."""
        if not raw_data:
            return {}

        # User info
        author_info = raw_data.get("author_portrait", "")
        author_name = raw_data.get("author_username", "")

        # Review content
        comment = raw_data.get("comment", "")
        rating = raw_data.get("rating_star", raw_data.get("rating", 0))

        # Time
        ctime = raw_data.get("ctime", 0)
        created_at = ""
        if ctime:
            with contextlib.suppress(Exception):
                created_at = datetime.fromtimestamp(ctime).isoformat()

        # Media (images/videos)
        images = raw_data.get("images", [])
        image_urls = [
            f"https://cf.shopee.co.id/file/{img}" if not img.startswith("http") else img
            for img in images
        ]

        videos = raw_data.get("videos", [])
        video_urls = []
        for video in videos:
            if isinstance(video, dict):
                url = video.get("url", "")
                if url:
                    video_urls.append(url)
            elif isinstance(video, str):
                video_urls.append(video)

        # Product variation
        product_items = raw_data.get("product_items", [])
        variation = ""
        if product_items:
            item = product_items[0] if product_items else {}
            variation = item.get("model_name", "")

        # Likes
        likes = raw_data.get("like_count", 0)

        # Shop reply
        reply = raw_data.get("itemrep", {})
        shop_reply = ""
        if reply:
            shop_reply = reply.get("comment", "")

        return {
            "rating_id": raw_data.get("cmtid", raw_data.get("id", 0)),
            "item_id": raw_data.get("itemid", 0),
            "shop_id": raw_data.get("shopid", 0),
            "order_id": raw_data.get("orderid", 0),
            "author": {
                "user_id": raw_data.get("userid", 0),
                "username": author_name,
                "avatar": author_info,
            },
            "rating": rating,
            "comment": comment,
            "variation": variation,
            "images": image_urls,
            "videos": video_urls,
            "likes": likes,
            "shop_reply": shop_reply,
            "is_anonymous": raw_data.get("anonymous", False),
            "created_at": created_at,
            "tags": raw_data.get("tags", []),
        }

    async def extract(self, page: Page) -> dict[str, Any]:
        """Extract data from current page (interface compliance)."""
        summary = await self._extract_review_summary(page)
        return {"summary": summary}
