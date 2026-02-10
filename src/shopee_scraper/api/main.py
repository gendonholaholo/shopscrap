"""FastAPI application factory and configuration."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shopee_scraper import __version__
from shopee_scraper.api.dependencies import (
    cleanup_redis,
    cleanup_scraper_service,
    get_redis,
    get_scraper_service,
)
from shopee_scraper.api.jobs import cleanup_job_queue, setup_job_queue
from shopee_scraper.api.rate_limiter import setup_rate_limiter
from shopee_scraper.api.routes import (
    extension_router,
    health_router,
    jobs_router,
    products_router,
    reviews_router,
    session_router,
    websocket_router,
)
from shopee_scraper.extension.manager import (
    cleanup_extension_manager,
    init_extension_manager,
)
from shopee_scraper.utils.config import get_settings
from shopee_scraper.utils.logging import get_logger


if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager."""
    settings = get_settings()
    logger.info(
        "Starting Shopee Scraper API",
        version=__version__,
        env=settings.env,
        debug=settings.debug,
    )

    # Log security warnings for production
    security_warnings = settings.get_security_warnings()
    if security_warnings:
        logger.warning(
            "SECURITY WARNINGS DETECTED",
            environment=settings.env,
            warnings=security_warnings,
        )
        for warning in security_warnings:
            logger.warning(f"[SECURITY] {warning}")

    # Startup: Initialize Redis and job queue
    try:
        redis = await get_redis()
        scraper_service = await get_scraper_service()

        # Initialize caching if enabled
        if settings.cache.enabled:
            from shopee_scraper.services.cache import ProductCache, ReviewCache

            product_cache = ProductCache(
                redis=redis,
                ttl_seconds=settings.cache.product_ttl_seconds,
            )
            review_cache = ReviewCache(
                redis=redis,
                ttl_seconds=settings.cache.review_ttl_seconds,
            )
            scraper_service.set_caches(
                product_cache=product_cache,
                review_cache=review_cache,
            )
            logger.info(
                "Caching enabled",
                product_ttl=settings.cache.product_ttl_seconds,
                review_ttl=settings.cache.review_ttl_seconds,
            )

        await setup_job_queue(
            redis=redis,
            settings=settings.job_queue,
            scraper_service=scraper_service,
        )
        logger.info("Job queue initialized with Redis backend")

        # Initialize Extension Manager
        await init_extension_manager(
            task_timeout=settings.extension.task_timeout_seconds,
            heartbeat_timeout=settings.extension.heartbeat_timeout_seconds,
        )
        logger.info("Extension manager initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize job queue: {e}")

    yield

    # Shutdown
    logger.info("Shutting down Shopee Scraper API")
    await cleanup_extension_manager()
    await cleanup_job_queue()
    await cleanup_redis()
    await cleanup_scraper_service()


def setup_cors(app: FastAPI) -> None:
    """Setup CORS middleware based on configuration."""
    settings = get_settings()
    cors_config = settings.cors

    if not cors_config.enabled:
        logger.info("CORS is DISABLED")
        return

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_config.get_origins_list(),
        allow_credentials=cors_config.allow_credentials,
        allow_methods=cors_config.get_methods_list(),
        allow_headers=cors_config.get_headers_list(),
        max_age=cors_config.max_age,
    )

    logger.info(
        "CORS ENABLED",
        origins=cors_config.allow_origins,
        methods=cors_config.allow_methods,
        credentials=cors_config.allow_credentials,
    )


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    settings = get_settings()

    # Build description based on settings
    rate_limit_info = (
        f"Rate limited to {settings.rate_limit.requests_per_minute} req/min"
        if settings.rate_limit.enabled
        else "No rate limiting (development mode)"
    )

    auth_info = (
        "**Required** - Pass API key via `X-API-Key` header or `api_key` query param"
        if settings.auth.auth_enabled
        else "No authentication required (development mode)"
    )

    app = FastAPI(
        title="Shopee Scraper API",
        description=f"""
## RESTful API for Shopee Scraper

This API provides endpoints to scrape product data from Shopee.co.id

### Features
- **Session**: Upload cookies from browser extension for authentication
- **Products**: Scrape product list and details (async)
- **Reviews**: Retrieve product reviews
- **Jobs**: Monitor and manage background scraping jobs

### Authentication
{auth_info}

### Rate Limiting
{rate_limit_info}

### Environment
Running in **{settings.env}** mode.
        """,
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
        debug=settings.debug,
    )

    # Log auth status
    if settings.auth.auth_enabled:
        key_count = len(settings.auth.get_keys_list())
        logger.info(f"API Authentication ENABLED ({key_count} key(s) configured)")
    else:
        logger.info("API Authentication DISABLED")

    # Setup CORS (configurable)
    setup_cors(app)

    # Setup Rate Limiter (configurable)
    setup_rate_limiter(app)

    # Exception handlers
    @app.exception_handler(Exception)
    async def global_exception_handler(
        _request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """Handle uncaught exceptions."""
        # In production, hide error details
        if settings.env == "production" and not settings.debug:
            error_detail = "An unexpected error occurred"
            logger.error("Unhandled exception", error=str(exc), exc_info=True)
        else:
            error_detail = str(exc)

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": "Internal server error",
                "detail": error_detail,
            },
        )

    # Register routers (order determines Swagger display order)
    app.include_router(session_router, prefix="/api/v1")  # Session first
    app.include_router(products_router, prefix="/api/v1")
    app.include_router(reviews_router, prefix="/api/v1")
    app.include_router(jobs_router, prefix="/api/v1")
    app.include_router(websocket_router, prefix="/api/v1")  # WebSocket for real-time
    app.include_router(extension_router, prefix="/api/v1")  # Chrome Extension gateway
    app.include_router(health_router)  # Health last

    return app


# Application instance
app = create_app()
