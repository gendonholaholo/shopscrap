"""
Shopee Scraper - High-performance scraper using Camoufox anti-detect browser.

Usage:
    from shopee_scraper import ShopeeScraper

    async with ShopeeScraper() as scraper:
        products = await scraper.search("laptop", max_pages=2)
        product = await scraper.get_product(shop_id, item_id)
        reviews = await scraper.get_reviews(shop_id, item_id)
"""

__version__ = "0.2.0"
__author__ = "Your Name"

from shopee_scraper.core.browser import BrowserManager
from shopee_scraper.core.scraper import ShopeeScraper
from shopee_scraper.core.session import SessionManager


__all__ = [
    "BrowserManager",
    "SessionManager",
    "ShopeeScraper",
    "__version__",
]
