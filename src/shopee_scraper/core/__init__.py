"""Core module - Browser automation and scraping engine."""

from shopee_scraper.core.browser import BrowserManager
from shopee_scraper.core.scraper import ShopeeScraper
from shopee_scraper.core.session import SessionManager


__all__ = [
    "BrowserManager",
    "SessionManager",
    "ShopeeScraper",
]
