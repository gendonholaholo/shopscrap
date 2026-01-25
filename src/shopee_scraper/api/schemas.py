"""Pydantic schemas for RESTful API request/response models."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from shopee_scraper.api.jobs import JobStatus


# =============================================================================
# Enums
# =============================================================================


class SortOrder(str, Enum):
    """Product sort order options."""

    RELEVANCY = "relevancy"
    SALES = "sales"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"


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
# Product Schemas (aligned with ProductOutput dataclass)
# =============================================================================


class SellerSchema(BaseModel):
    """Seller information."""

    id: str
    name: str
    url: str
    location: str
    isOfficialStore: bool


class CategorySchema(BaseModel):
    """Product category information."""

    id: str
    name: str
    breadcrumb: list[str] = Field(default_factory=list)


class SpecsSchema(BaseModel):
    """Product specifications."""

    condition: str = "new"
    minOrder: int = 1
    weight: int = 0
    sku: str | None = None
    customSpecs: dict[str, str] = Field(default_factory=dict)


class VariantOptionSchema(BaseModel):
    """Option within a variant."""

    name: str
    price: int
    stock: int
    isActive: bool


class VariantSchema(BaseModel):
    """Product variant."""

    name: str
    options: list[VariantOptionSchema] = Field(default_factory=list)


class ShippingSchema(BaseModel):
    """Shipping information."""

    freeShipping: bool = False
    insuranceRequired: bool = False


class ReviewerSchema(BaseModel):
    """Reviewer information."""

    id: str
    username: str
    displayName: str
    avatarUrl: str
    isVerifiedPurchase: bool
    memberSince: str
    totalReviews: int
    helpfulVotes: int


class ReviewItemSchema(BaseModel):
    """Individual review item."""

    id: str
    reviewer: ReviewerSchema
    rating: int = Field(..., ge=1, le=5)
    title: str
    content: str
    images: list[str] = Field(default_factory=list)
    videos: list[str] = Field(default_factory=list)
    variantPurchased: str
    purchaseDate: str
    reviewDate: str
    isEdited: bool
    helpfulCount: int
    replyFromSeller: str | None = None
    replyDate: str | None = None


class ReviewsSchema(BaseModel):
    """Reviews summary and items."""

    rating: float
    count: int
    breakdown: dict[str, int] = Field(default_factory=dict)
    withPhotos: int = 0
    withDescription: int = 0
    items: list[ReviewItemSchema] = Field(default_factory=list)


class LabelsSchema(BaseModel):
    """Product labels/badges."""

    isCOD: bool = False
    isWholesale: bool = False
    isCashback: bool = False


class ProductSchema(BaseModel):
    """Complete product schema matching ProductOutput format."""

    id: str
    url: str
    marketplace: str = "shopee"
    title: str
    price: int
    thumbnail: str
    images: list[str] = Field(default_factory=list)
    seller: SellerSchema
    rating: float = 0.0
    reviewCount: int = 0
    soldCount: int = 0
    stock: int = 0
    isAvailable: bool = True
    description: str = ""
    descriptionHtml: str = ""
    category: CategorySchema
    specifications: SpecsSchema
    variants: list[VariantSchema] = Field(default_factory=list)
    shipping: ShippingSchema
    reviews: ReviewsSchema
    labels: LabelsSchema
    scrapedAt: str
    scrapeVersion: str = "1.0.0"


class ExportSchema(BaseModel):
    """Top-level export wrapper matching ExportOutput format."""

    exportedAt: str
    marketplace: str = "shopee"
    count: int
    products: list[ProductSchema]


# =============================================================================
# API Response Schemas
# =============================================================================


class ProductResponse(BaseResponse):
    """Single product response."""

    data: dict[str, Any]
    links: dict[str, str] = Field(default_factory=dict)


class ProductListResponse(BaseResponse):
    """Product list response with export format."""

    data: ExportSchema
    links: dict[str, str] = Field(default_factory=dict)


class ProductLinks(BaseModel):
    """HATEOAS links for product resource."""

    self: str
    reviews: str


# =============================================================================
# Review API Schemas
# =============================================================================


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
