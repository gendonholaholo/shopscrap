"""FastAPI dependencies for dependency injection."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from shopee_scraper.api.auth import get_api_key, optional_api_key
from shopee_scraper.services.scraper_service import ScraperService


# Global service instance (singleton pattern)
_scraper_service: ScraperService | None = None


async def get_scraper_service() -> ScraperService:
    """Get or create scraper service instance."""
    global _scraper_service  # noqa: PLW0603
    if _scraper_service is None:
        _scraper_service = ScraperService(headless=True)
    return _scraper_service


async def cleanup_scraper_service() -> None:
    """Cleanup scraper service on shutdown."""
    global _scraper_service  # noqa: PLW0603
    if _scraper_service:
        await _scraper_service.close()
        _scraper_service = None


# Type aliases for dependency injection
ScraperServiceDep = Annotated[ScraperService, Depends(get_scraper_service)]

# API Key dependencies
RequireApiKey = Annotated[str, Depends(get_api_key)]
OptionalApiKey = Annotated[str | None, Depends(optional_api_key)]
