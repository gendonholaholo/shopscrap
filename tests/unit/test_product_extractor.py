"""Unit tests for ProductExtractor.parse() — BFF and legacy format support."""

from __future__ import annotations

from unittest.mock import MagicMock

from shopee_scraper.extractors.product import ProductExtractor


class TestProductExtractorParse:
    """Tests for ProductExtractor.parse() method."""

    def setup_method(self) -> None:
        mock_browser = MagicMock()
        self.extractor = ProductExtractor(browser=mock_browser)

    def test_parse_legacy_format(self) -> None:
        """Legacy format (/api/v4/item/get) should parse correctly."""
        raw = {
            "item": {
                "itemid": 12345,
                "shopid": 67890,
                "name": "Legacy Product",
                "description": "Legacy description",
                "price": 500000000000,
                "price_min": 500000000000,
                "price_max": 700000000000,
                "stock": 25,
                "sold": 100,
                "images": ["img001"],
                "models": [
                    {
                        "modelid": 1,
                        "name": "Variant A",
                        "price": 500000000000,
                        "stock": 15,
                        "sold": 50,
                    },
                ],
                "tier_variations": [
                    {"name": "Type", "options": ["Variant A"]},
                ],
                "categories": [
                    {"display_name": "Electronics"},
                ],
                "item_rating": {
                    "rating_star": 4.5,
                    "rating_count": [0, 1, 2, 5, 10, 82],
                },
                "cmt_count": 100,
                "attributes": [{"name": "Brand", "value": "Test"}],
            },
            "shop_info": {
                "name": "Test Shop",
                "account": {"username": "testshop"},
                "shop_location": "Jakarta",
                "is_official_shop": True,
            },
        }

        result = self.extractor.parse(raw)
        assert result["item_id"] == 12345
        assert result["name"] == "Legacy Product"
        assert result["description"] == "Legacy description"
        assert result["price"] == 5000000  # 500000000000 / 100000
        assert result["price_max"] == 7000000
        assert result["stock"] == 25
        assert result["sold"] == 100
        assert result["rating"] == 4.5
        assert result["rating_count"] == 100
        assert result["shop"]["name"] == "Test Shop"
        assert result["shop"]["is_official"] is True
        assert len(result["images"]) == 1
        assert len(result["variants"]) == 1
        assert len(result["variations"]) == 1

    def test_parse_bff_format(self) -> None:
        """BFF format (/api/v4/pdp/get_pc) should parse correctly."""
        raw = {
            "item": {
                "item_id": 55555,
                "shop_id": 66666,
                "title": "BFF Product",
                "stock": 10,
                "condition": 1,
                "models": [
                    {
                        "model_id": 1,
                        "name": "Size M",
                        "price": 300000000000,
                        "stock": 5,
                    },
                ],
                "tier_variations": [
                    {"name": "Size", "options": ["Size M"]},
                ],
                "categories": [
                    {"display_name": "Fashion"},
                ],
            },
            "product_price": {
                "price": {
                    "single_value": 300000000000,
                    "range_min": 300000000000,
                    "range_max": 500000000000,
                },
                "price_before_discount": {
                    "single_value": 400000000000,
                },
            },
            "product_detail": {
                "description": "BFF description from product_detail",
            },
            "product_images": {"images": ["bff_img1", "bff_img2"]},
            "shop_detailed": {
                "name": "BFF Shop",
                "account": {"username": "bffshop"},
                "shop_location": "Bandung",
                "is_official_shop": False,
                "rating_star": 4.8,
            },
            "product_review": {
                "rating_star": 4.7,
                "total_rating_count": 200,
                "rating_count": [0, 2, 3, 10, 50, 135],
                "historical_sold": 500,
            },
        }

        result = self.extractor.parse(raw)
        assert result["item_id"] == 55555
        assert result["name"] == "BFF Product"
        assert result["description"] == "BFF description from product_detail"
        assert result["price"] == 3000000  # 300000000000 / 100000
        assert result["price_max"] == 5000000
        assert result["price_before_discount"] == 4000000
        assert result["stock"] == 10
        assert result["sold"] == 500
        assert result["rating"] == 4.7
        assert result["rating_count"] == 200
        assert result["shop"]["name"] == "BFF Shop"
        assert result["shop"]["username"] == "bffshop"
        assert result["shop"]["location"] == "Bandung"
        assert len(result["images"]) == 2
        assert len(result["variants"]) == 1
        assert len(result["variations"]) == 1

    def test_parse_bff_description_fallback_to_item(self) -> None:
        """BFF with empty product_detail falls back to item.description."""
        raw = {
            "item": {
                "item_id": 77777,
                "shop_id": 88888,
                "title": "Fallback Test",
                "description": "Fallback from item",
                "stock": 1,
                "condition": 1,
            },
            "product_price": {
                "price": {"single_value": 100000000000},
            },
            "product_detail": {},
            "product_images": {"images": []},
            "shop_detailed": {},
            "product_review": {},
        }

        result = self.extractor.parse(raw)
        assert result["description"] == "Fallback from item"

    def test_parse_empty_data(self) -> None:
        result = self.extractor.parse({})
        assert result == {}

    def test_parse_no_item_id(self) -> None:
        raw = {"item": {"name": "No ID"}}
        result = self.extractor.parse(raw)
        assert result == {}

    def test_parse_bff_hidden_stock(self) -> None:
        """BFF format with stock=None uses stock_display fallback."""
        raw = {
            "item": {
                "item_id": 99999,
                "shop_id": 11111,
                "title": "Hidden Stock",
                "stock": None,
                "stock_display": "Stok: 5",
                "condition": 1,
            },
            "product_price": {
                "price": {"single_value": 50000000000},
            },
            "product_images": {"images": []},
            "shop_detailed": {},
            "product_review": {},
        }

        result = self.extractor.parse(raw)
        assert result["stock"] == 1  # Available based on stock_display
