"""Pydantic schemas for RESTful API request/response models."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================


class SortOrder(str, Enum):
    """Product sort order options."""

    RELEVANCY = "relevancy"
    SALES = "sales"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"


class JobStatus(str, Enum):
    """Async job status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# =============================================================================
# Base Schemas
# =============================================================================


class BaseResponse(BaseModel):
    """Base response with common fields."""

    success: bool = True
    message: str = "OK"


class ErrorResponse(BaseModel):
    """Error response schema."""

    success: bool = False
    error: str
    detail: str | None = None


class PaginationMeta(BaseModel):
    """Pagination metadata."""

    total: int
    page: int = 1
    per_page: int = 60
    total_pages: int = 1


# =============================================================================
# Product Schemas
# =============================================================================


class ProductBase(BaseModel):
    """Base product fields."""

    item_id: int
    shop_id: int
    name: str
    price: float
    original_price: float | None = None
    discount: float | None = None
    sold: int = 0
    stock: int = 0
    rating: float = 0.0
    rating_count: int = 0
    image_url: str | None = None
    shop_name: str | None = None
    location: str | None = None


class ProductDetail(ProductBase):
    """Detailed product information."""

    description: str | None = None
    categories: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    images: list[str] = Field(default_factory=list)
    variations: list[dict[str, Any]] = Field(default_factory=list)


class ProductLinks(BaseModel):
    """HATEOAS links for product resource."""

    self: str
    reviews: str


# =============================================================================
# Review Schemas
# =============================================================================


class ReviewAuthor(BaseModel):
    """Review author information."""

    user_id: int | None = None
    username: str
    avatar: str | None = None


class Review(BaseModel):
    """Single review."""

    rating: int = Field(..., ge=1, le=5)
    comment: str | None = None
    author: ReviewAuthor
    created_at: str | None = None
    images: list[str] = Field(default_factory=list)
    likes: int = 0


class ReviewsMeta(BaseModel):
    """Reviews metadata."""

    shop_id: int
    item_id: int
    total_count: int
    average_rating: float | None = None


class ReviewsLinks(BaseModel):
    """HATEOAS links for reviews."""

    self: str
    product: str


class ReviewsResponse(BaseResponse):
    """Reviews response."""

    meta: ReviewsMeta
    data: list[dict[str, Any]]
    links: ReviewsLinks


class ReviewSummary(BaseModel):
    """Review summary statistics."""

    total_reviews: int
    average_rating: float
    rating_distribution: dict[str, int] = Field(default_factory=dict)


# =============================================================================
# Job Schemas (for async operations)
# =============================================================================


class JobCreate(BaseModel):
    """Create async job request."""

    keyword: str = Field(..., min_length=1)
    max_products: int = Field(default=10, ge=1, le=100)
    include_reviews: bool = False
    webhook_url: str | None = None


class JobResponse(BaseModel):
    """Async job response."""

    job_id: str
    status: JobStatus
    created_at: str
    links: dict[str, str]


class JobResult(BaseModel):
    """Job result when completed."""

    job_id: str
    status: JobStatus
    created_at: str
    completed_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


# =============================================================================
# Health Check
# =============================================================================


class ComponentHealthSchema(BaseModel):
    """Individual component health status."""

    name: str
    status: str  # "healthy", "degraded", "unhealthy"
    message: str | None = None
    latency_ms: float | None = None


class HealthResponse(BaseModel):
    """Comprehensive health check response."""

    status: str  # "healthy", "degraded", "unhealthy"
    version: str
    uptime_seconds: float
    timestamp: str

    # Component status
    scraper_ready: bool = False
    browser_available: bool = False

    # Detailed checks
    components: list[ComponentHealthSchema] = Field(default_factory=list)

    # Metrics
    total_checks: int = 0
    healthy_checks: int = 0
    degraded_checks: int = 0
    unhealthy_checks: int = 0


class LivenessResponse(BaseModel):
    """Simple liveness check response."""

    status: str = "alive"
    timestamp: str


class ReadinessResponse(BaseModel):
    """Readiness check response."""

    status: str  # "ready", "not_ready"
    ready: bool
    checks: list[ComponentHealthSchema] = Field(default_factory=list)
