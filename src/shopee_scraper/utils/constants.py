"""Constants used throughout the Shopee Scraper application."""

from __future__ import annotations


# =============================================================================
# URLs
# =============================================================================

BASE_URL = "https://shopee.co.id"
LOGIN_URL = f"{BASE_URL}/buyer/login"

# API Endpoints (primary endpoints)
SEARCH_API = "/api/v4/search/search_items"
PRODUCT_API = "/api/v4/pdp/get_pc"
ITEM_API = "/api/v4/item/get"
REVIEW_API = "/api/v4/pdp/get_rw"
REVIEW_RATINGS_API = "/api/v2/item/get_ratings"
RECOMMEND_API = "/api/v4/recommend/recommend"
SEARCH_HINT_API = "/api/v4/search/search_hint"

# API Pattern Lists (for network interception)
SEARCH_API_PATTERNS = [SEARCH_API, RECOMMEND_API, SEARCH_HINT_API]
PRODUCT_API_PATTERNS = [PRODUCT_API, ITEM_API]
REVIEW_API_PATTERNS = [REVIEW_RATINGS_API, REVIEW_API]
ALL_API_PATTERNS = SEARCH_API_PATTERNS + PRODUCT_API_PATTERNS + REVIEW_API_PATTERNS

# =============================================================================
# Price Conversion
# =============================================================================

# Shopee stores prices in a format that needs division by this factor
PRICE_DIVISOR = 100000

# =============================================================================
# Default Values
# =============================================================================

# Timeouts (in milliseconds)
DEFAULT_TIMEOUT = 30000
NAVIGATION_TIMEOUT = 60000

# Delays (in seconds)
MIN_DELAY = 1.0
MAX_DELAY = 3.0
SHORT_DELAY = 0.1  # Quick micro-delay for loops
POST_ACTION_DELAY = 2.0  # Delay after significant actions (captcha, navigation)
VERIFICATION_WAIT_DELAY = 5.0  # Wait time when checking verification status
PAGE_LOAD_DELAY = 3.0  # Wait for page elements to load

# Retry settings
DEFAULT_MAX_RETRIES = 3
CAPTCHA_POLL_INTERVAL = 2.0  # Interval for polling captcha solution status

# =============================================================================
# Verification URL Patterns
# =============================================================================

VERIFY_URL_PATTERN = "/verify/"
LOGIN_URL_PATTERN = "/buyer/login"
