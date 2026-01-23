"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture
def sample_product_data() -> dict:
    """Sample product data for testing."""
    return {
        "item_id": 12345678,
        "shop_id": 87654321,
        "name": "Test Product",
        "price": 150000.0,
        "stock": 100,
        "sold": 50,
        "rating": 4.5,
        "url": "https://shopee.co.id/product/87654321/12345678",
    }


@pytest.fixture
def sample_search_results() -> list[dict]:
    """Sample search results for testing."""
    return [
        {"item_id": 1, "name": "Product 1", "price": 10000},
        {"item_id": 2, "name": "Product 2", "price": 20000},
        {"item_id": 3, "name": "Product 3", "price": 30000},
    ]
