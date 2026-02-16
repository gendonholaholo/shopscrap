"""RESTful API package for Shopee Scraper."""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from shopee_scraper.api.main import create_app as _create_app


def create_app() -> _create_app:
    """Lazy import of create_app to avoid circular imports."""
    from shopee_scraper.api.main import create_app as _create_app

    return _create_app()


__all__ = ["create_app"]
