"""Custom exceptions for the Shopee Scraper application."""

from __future__ import annotations


class ShopeeScraperError(Exception):
    """Base exception for all scraper errors."""

    pass


# =============================================================================
# Browser Errors
# =============================================================================


class BrowserError(ShopeeScraperError):
    """Base exception for browser-related errors."""

    pass


class BrowserNotInitializedError(BrowserError):
    """Raised when browser is accessed before initialization."""

    pass


class NavigationError(BrowserError):
    """Raised when page navigation fails."""

    pass


class PageLoadError(BrowserError):
    """Raised when page content fails to load."""

    pass


# =============================================================================
# Verification/CAPTCHA Errors
# =============================================================================


class VerificationError(ShopeeScraperError):
    """Base exception for verification-related errors."""

    pass


class CaptchaError(VerificationError):
    """Raised when CAPTCHA solving fails."""

    pass


class LoginRequiredError(VerificationError):
    """Raised when login is required to proceed."""

    pass


class TrafficVerificationError(VerificationError):
    """Raised when traffic verification cannot be resolved."""

    pass


# =============================================================================
# Extraction Errors
# =============================================================================


class ExtractionError(ShopeeScraperError):
    """Base exception for data extraction errors."""

    pass


class ProductNotFoundError(ExtractionError):
    """Raised when a product cannot be found."""

    pass


class NetworkInterceptionError(ExtractionError):
    """Raised when API response interception fails."""

    pass


class ParseError(ExtractionError):
    """Raised when data parsing fails."""

    pass


# =============================================================================
# Proxy Errors
# =============================================================================


class ProxyError(ShopeeScraperError):
    """Base exception for proxy-related errors."""

    pass


class ProxyConnectionError(ProxyError):
    """Raised when proxy connection fails."""

    pass


class ProxyTimeoutError(ProxyError):
    """Raised when proxy connection times out."""

    pass


# =============================================================================
# API/Service Errors
# =============================================================================


class ServiceError(ShopeeScraperError):
    """Base exception for service-layer errors."""

    pass


class QueueFullError(ServiceError):
    """Raised when job queue is full."""

    pass


class RateLimitError(ServiceError):
    """Raised when rate limit is exceeded."""

    pass


class CacheError(ServiceError):
    """Raised when cache operations fail."""

    pass


# =============================================================================
# Configuration Errors
# =============================================================================


class ConfigurationError(ShopeeScraperError):
    """Raised when configuration is invalid."""

    pass
