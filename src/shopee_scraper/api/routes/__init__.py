"""API routes package."""

from shopee_scraper.api.routes.extension import router as extension_router
from shopee_scraper.api.routes.health import router as health_router
from shopee_scraper.api.routes.jobs import router as jobs_router
from shopee_scraper.api.routes.products import router as products_router
from shopee_scraper.api.routes.reviews import router as reviews_router
from shopee_scraper.api.routes.session import router as session_router
from shopee_scraper.api.routes.websocket import router as websocket_router


__all__ = [
    "extension_router",
    "health_router",
    "jobs_router",
    "products_router",
    "reviews_router",
    "session_router",
    "websocket_router",
]
