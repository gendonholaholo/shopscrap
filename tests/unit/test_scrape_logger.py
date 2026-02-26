"""Unit tests for ScrapeLogger."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shopee_scraper.storage.scrape_logger import ScrapeLogger


SAMPLE_PRODUCT = {
    "item_id": 12345,
    "shop_id": 67890,
    "name": "Test Product",
    "description": "Test description",
    "price": 150000.0,
    "price_min": 150000.0,
    "price_max": 200000.0,
    "price_before_discount": 180000.0,
    "stock": 10,
    "sold": 50,
    "rating": 4.5,
    "rating_count": 100,
    "images": ["https://cf.shopee.co.id/file/img1"],
    "variants": [{"model_id": 1, "name": "A", "price": 150000, "stock": 5}],
    "variations": [{"name": "Type", "options": ["A", "B"]}],
    "category_id": 111,
    "category_path": ["Electronics", "Phones"],
    "condition": "new",
    "shop": {
        "shop_id": 67890,
        "name": "Test Shop",
        "username": "testshop",
        "location": "Jakarta",
        "rating": 4.8,
        "is_official": True,
    },
    "attributes": [{"name": "Brand", "value": "Test"}],
    "url": "https://shopee.co.id/product/67890/12345",
}


class TestScrapeLogger:
    """Tests for ScrapeLogger."""

    def setup_method(self) -> None:
        self.logger = ScrapeLogger()

    @pytest.fixture
    def mock_session(self):
        """Create a mock async session context manager."""
        session = AsyncMock()
        session.add = MagicMock()
        return session

    async def test_log_product(self, mock_session) -> None:
        """log_product should create a ScrapeProduct record."""
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "shopee_scraper.storage.scrape_logger.get_session",
            return_value=mock_ctx,
        ):
            await self.logger.log_product(
                normalized_data=SAMPLE_PRODUCT,
                source="extension",
                api_format="bff",
                raw_keys=["item", "product_price", "product_detail"],
                job_id="test-job-123",
            )

        mock_session.add.assert_called_once()
        record = mock_session.add.call_args[0][0]
        assert record.item_id == 12345
        assert record.shop_id == 67890
        assert record.name == "Test Product"
        assert record.source == "extension"
        assert record.api_format == "bff"
        assert record.job_id == "test-job-123"

    async def test_log_product_handles_db_failure(self) -> None:
        """log_product should not raise on database errors."""
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("DB not initialized"))

        with patch(
            "shopee_scraper.storage.scrape_logger.get_session",
            return_value=mock_ctx,
        ):
            # Should not raise
            await self.logger.log_product(
                normalized_data=SAMPLE_PRODUCT,
                source="browser",
                api_format="legacy",
            )

    async def test_log_products_batch(self, mock_session) -> None:
        """log_products should call log_product for each product."""
        products = [SAMPLE_PRODUCT, {**SAMPLE_PRODUCT, "item_id": 99999}]

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "shopee_scraper.storage.scrape_logger.get_session",
            return_value=mock_ctx,
        ):
            await self.logger.log_products(
                products=products,
                source="extension",
                api_format="bff",
                job_id="batch-job-456",
            )

        assert mock_session.add.call_count == 2
