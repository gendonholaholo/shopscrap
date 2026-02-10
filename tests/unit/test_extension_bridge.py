"""Unit tests for extension bridge."""

from __future__ import annotations

from shopee_scraper.extension.bridge import ExtensionBridge
from shopee_scraper.models.output import ProductOutput


class TestProcessSearchResult:
    """Tests for processing raw search API responses."""

    def setup_method(self) -> None:
        self.bridge = ExtensionBridge()

    def test_basic_search_result(self) -> None:
        raw = {
            "items": [
                {
                    "item_basic": {
                        "itemid": 12345,
                        "shopid": 67890,
                        "name": "Laptop Gaming ASUS",
                        "price": 1500000000000,
                        "price_min": 1500000000000,
                        "stock": 50,
                        "sold": 100,
                        "images": ["abc123"],
                        "item_rating": {
                            "rating_star": 4.8,
                            "rating_count": [0, 1, 2, 5, 10, 82],
                        },
                        "shop_location": "Jakarta",
                        "is_official_shop": True,
                    }
                }
            ]
        }

        products = self.bridge.process_search_result(raw)
        assert len(products) == 1
        assert isinstance(products[0], ProductOutput)
        assert products[0].title == "Laptop Gaming ASUS"
        # Price: 1500000000000 / 100000 = 15000000
        assert products[0].price == 15000000

    def test_empty_items(self) -> None:
        products = self.bridge.process_search_result({"items": []})
        assert products == []

    def test_flat_items_no_item_basic(self) -> None:
        """Items without item_basic wrapper should also work."""
        raw = {
            "items": [
                {
                    "itemid": 111,
                    "shopid": 222,
                    "name": "Test Product",
                    "price": 50000000000,
                    "price_min": 50000000000,
                    "stock": 10,
                    "sold": 5,
                    "images": [],
                    "item_rating": {
                        "rating_star": 3.0,
                        "rating_count": [0, 0, 0, 5, 0, 0],
                    },
                }
            ]
        }
        products = self.bridge.process_search_result(raw)
        assert len(products) == 1
        assert products[0].title == "Test Product"

    def test_alternate_data_structure(self) -> None:
        """Some API responses nest items under data.items."""
        raw = {
            "data": {
                "items": [
                    {
                        "itemid": 333,
                        "shopid": 444,
                        "name": "Nested Item",
                        "price": 100000000000,
                        "price_min": 100000000000,
                        "stock": 1,
                        "images": [],
                        "item_rating": {"rating_star": 5.0, "rating_count": [0]},
                    }
                ]
            }
        }
        products = self.bridge.process_search_result(raw)
        assert len(products) == 1


class TestProcessProductResult:
    """Tests for processing raw product API responses."""

    def setup_method(self) -> None:
        self.bridge = ExtensionBridge()

    def test_pdp_get_pc_format(self) -> None:
        raw = {
            "data": {
                "item": {
                    "itemid": 99999,
                    "shopid": 88888,
                    "name": "Smartphone Samsung Galaxy",
                    "description": "Brand new phone",
                    "price": 500000000000,
                    "price_min": 500000000000,
                    "price_max": 700000000000,
                    "stock": 25,
                    "sold": 200,
                    "images": ["img001", "img002"],
                    "models": [
                        {
                            "modelid": 1,
                            "name": "128GB",
                            "price": 500000000000,
                            "stock": 15,
                        },
                        {
                            "modelid": 2,
                            "name": "256GB",
                            "price": 700000000000,
                            "stock": 10,
                        },
                    ],
                    "tier_variations": [
                        {
                            "name": "Storage",
                            "options": ["128GB", "256GB"],
                        }
                    ],
                    "categories": [
                        {"display_name": "Electronics"},
                        {"display_name": "Phones"},
                    ],
                    "item_rating": {
                        "rating_star": 4.5,
                        "rating_count": [0, 5, 10, 20, 50, 115],
                    },
                    "cmt_count": 200,
                    "attributes": [{"name": "Brand", "value": "Samsung"}],
                },
                "shop_info": {
                    "name": "Samsung Official",
                    "account": {"username": "samsungofficial"},
                    "shop_location": "Jakarta",
                    "is_official_shop": True,
                },
            }
        }

        product = self.bridge.process_product_result(raw)
        assert product is not None
        assert isinstance(product, ProductOutput)
        assert product.title == "Smartphone Samsung Galaxy"
        assert product.price == 5000000  # 500000000000 / 100000
        assert len(product.images) == 2
        assert "img001" in product.images[0]

    def test_empty_data(self) -> None:
        product = self.bridge.process_product_result({})
        assert product is None

    def test_no_itemid(self) -> None:
        raw = {"data": {"item": {"name": "No ID"}}}
        product = self.bridge.process_product_result(raw)
        assert product is None


class TestProcessReviewsResult:
    """Tests for processing raw reviews API responses."""

    def setup_method(self) -> None:
        self.bridge = ExtensionBridge()

    def test_basic_reviews(self) -> None:
        raw = {
            "data": {
                "ratings": [
                    {
                        "cmtid": 12345,
                        "rating_star": 5,
                        "comment": "Barang bagus!",
                        "images": ["rev_img1"],
                        "videos": [],
                        "like_count": 3,
                        "ctime": 1700000000,
                        "author_username": "buyer1",
                        "author_shopid": 99,
                        "author_portrait": "avatar1",
                    },
                    {
                        "cmtid": 12346,
                        "rating_star": 4,
                        "comment": "Lumayan",
                        "images": [],
                        "videos": [],
                        "like_count": 0,
                        "ctime": 1700001000,
                        "author_username": "buyer2",
                        "author_shopid": 100,
                        "author_portrait": "",
                    },
                ]
            }
        }

        reviews = self.bridge.process_reviews_result(raw)
        assert len(reviews) == 2
        assert reviews[0]["rating"] == 5
        assert reviews[0]["comment"] == "Barang bagus!"
        assert reviews[0]["author"]["username"] == "buyer1"
        assert reviews[1]["rating"] == 4

    def test_empty_ratings(self) -> None:
        reviews = self.bridge.process_reviews_result({"data": {"ratings": []}})
        assert reviews == []


class TestCreateExportOutput:
    """Tests for export output creation."""

    def setup_method(self) -> None:
        self.bridge = ExtensionBridge()

    def test_create_export(self) -> None:
        raw = {
            "items": [
                {
                    "itemid": 1,
                    "shopid": 2,
                    "name": "Product 1",
                    "price": 100000000000,
                    "price_min": 100000000000,
                    "stock": 10,
                    "images": [],
                    "item_rating": {"rating_star": 4.0, "rating_count": [0]},
                },
                {
                    "itemid": 3,
                    "shopid": 4,
                    "name": "Product 2",
                    "price": 200000000000,
                    "price_min": 200000000000,
                    "stock": 5,
                    "images": [],
                    "item_rating": {"rating_star": 3.5, "rating_count": [0]},
                },
            ]
        }

        products = self.bridge.process_search_result(raw)
        export = self.bridge.create_export_output(products)

        assert export["marketplace"] == "shopee"
        assert export["count"] == 2
        assert len(export["products"]) == 2
