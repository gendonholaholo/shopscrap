"""Data extractors for Shopee pages."""

from shopee_scraper.extractors.product import ProductExtractor
from shopee_scraper.extractors.review import ReviewExtractor
from shopee_scraper.extractors.search import SearchExtractor


__all__ = [
    "ProductExtractor",
    "ReviewExtractor",
    "SearchExtractor",
]
