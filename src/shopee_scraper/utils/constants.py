"""Constants used throughout the Shopee Scraper application."""

from __future__ import annotations


# =============================================================================
# URLs
# =============================================================================

BASE_URL = "https://shopee.co.id"
LOGIN_URL = f"{BASE_URL}/buyer/login"

# API Endpoints (used for URL matching in response interception)
SEARCH_API = "/api/v4/search/search_items"
PRODUCT_API = "/api/v4/pdp/get_pc"
ITEM_API = "/api/v4/item/get"
REVIEW_API = "/api/v4/pdp/get_rw"

# =============================================================================
# Price Conversion
# =============================================================================

# Shopee stores prices in a format that needs division by this factor
PRICE_DIVISOR = 100000

# =============================================================================
# Default Values
# =============================================================================

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Timeouts (in milliseconds)
DEFAULT_TIMEOUT = 30000
NAVIGATION_TIMEOUT = 60000

# Delays (in seconds)
MIN_DELAY = 1.0
MAX_DELAY = 3.0
