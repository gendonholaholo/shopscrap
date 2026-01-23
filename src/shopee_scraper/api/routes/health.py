"""Health check endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from shopee_scraper import __version__
from shopee_scraper.api.dependencies import ScraperServiceDep
from shopee_scraper.api.schemas import (
    ComponentHealthSchema,
    HealthResponse,
    LivenessResponse,
    ReadinessResponse,
)


router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Comprehensive health check",
    description="Detailed health status with all component checks.",
)
async def health_check(service: ScraperServiceDep) -> HealthResponse:
    """
    Return comprehensive health status.

    Includes:
    - Overall status (healthy/degraded/unhealthy)
    - Scraper initialization status
    - Browser availability
    - Component-level health checks
    - System metrics
    """
    health = await service.health_check()

    # Convert component dicts to schemas
    components = [
        ComponentHealthSchema(**comp) for comp in health.get("components", [])
    ]

    return HealthResponse(
        status=health["status"],
        version=__version__,
        uptime_seconds=health["uptime_seconds"],
        timestamp=health["timestamp"],
        scraper_ready=health["scraper_initialized"],
        browser_available=health["browser_available"],
        components=components,
        total_checks=health["total_checks"],
        healthy_checks=health["healthy_checks"],
        degraded_checks=health["degraded_checks"],
        unhealthy_checks=health["unhealthy_checks"],
    )


@router.get(
    "/health/live",
    response_model=LivenessResponse,
    summary="Liveness probe",
    description="Simple check if service is alive (Kubernetes liveness probe).",
)
async def liveness_check(service: ScraperServiceDep) -> LivenessResponse:
    """
    Liveness probe - is the service alive?

    This endpoint is designed for Kubernetes liveness probes.
    Returns 200 OK if the service process is running.
    """
    result = await service.liveness_check()
    return LivenessResponse(
        status=result["status"],
        timestamp=result["timestamp"],
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description="Check if service is ready to accept traffic (Kubernetes readiness probe).",
)
async def readiness_check(service: ScraperServiceDep) -> ReadinessResponse:
    """
    Readiness probe - is the service ready to handle requests?

    This endpoint is designed for Kubernetes readiness probes.
    Returns 200 if service is ready, 503 if not ready.

    Checks:
    - Disk space available
    - Storage directories accessible
    - Browser (Camoufox) available
    """
    result = await service.readiness_check()

    components = [ComponentHealthSchema(**comp) for comp in result.get("checks", [])]

    return ReadinessResponse(
        status=result["status"],
        ready=result["ready"],
        checks=components,
    )


@router.get(
    "/",
    summary="API root",
    description="API information and available endpoints.",
)
async def root() -> dict[str, Any]:
    """Return API info with HATEOAS links."""
    return {
        "name": "Shopee Scraper API",
        "version": __version__,
        "links": {
            "self": "/",
            "health": "/health",
            "session": "/api/v1/session",
            "products": "/api/v1/products",
            "jobs": "/api/v1/jobs",
            "docs": "/docs",
            "redoc": "/redoc",
        },
    }
