"""Output data models matching the target export format."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SellerInfo:
    """Seller information."""

    id: str
    name: str
    url: str
    location: str
    isOfficialStore: bool


@dataclass
class CategoryInfo:
    """Product category information."""

    id: str
    name: str
    breadcrumb: list[str]


@dataclass
class SpecsInfo:
    """Product specifications."""

    condition: str
    minOrder: int
    weight: int
    sku: str | None = None
    customSpecs: dict[str, str] = field(default_factory=dict)


@dataclass
class VariantOption:
    """Option within a variant."""

    name: str
    price: int
    stock: int
    isActive: bool


@dataclass
class VariantInfo:
    """Product variant (e.g., color, size)."""

    name: str
    options: list[VariantOption]


@dataclass
class ShippingInfo:
    """Shipping information."""

    freeShipping: bool
    insuranceRequired: bool


@dataclass
class ReviewerInfo:
    """Reviewer information."""

    id: str
    username: str
    displayName: str
    avatarUrl: str
    isVerifiedPurchase: bool
    memberSince: str
    totalReviews: int
    helpfulVotes: int


@dataclass
class ReviewInfo:
    """Individual review."""

    id: str
    reviewer: ReviewerInfo
    rating: int
    title: str
    content: str
    images: list[str]
    videos: list[str]
    variantPurchased: str
    purchaseDate: str
    reviewDate: str
    isEdited: bool
    helpfulCount: int
    replyFromSeller: str | None
    replyDate: str | None


@dataclass
class ReviewsInfo:
    """Reviews summary and items."""

    rating: float
    count: int
    breakdown: dict[str, int]
    withPhotos: int
    withDescription: int
    items: list[ReviewInfo]


@dataclass
class LabelsInfo:
    """Product labels/badges."""

    isCOD: bool
    isWholesale: bool
    isCashback: bool


@dataclass
class ProductOutput:
    """Complete product output format."""

    id: str
    url: str
    marketplace: str
    title: str
    price: int
    thumbnail: str
    images: list[str]
    seller: SellerInfo
    rating: float
    reviewCount: int
    soldCount: int
    stock: int
    isAvailable: bool
    description: str
    descriptionHtml: str
    category: CategoryInfo
    specifications: SpecsInfo
    variants: list[VariantInfo]
    shipping: ShippingInfo
    reviews: ReviewsInfo
    labels: LabelsInfo
    scrapedAt: str
    scrapeVersion: str


@dataclass
class ExportOutput:
    """Top-level export wrapper."""

    exportedAt: str
    marketplace: str
    count: int
    products: list[ProductOutput]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return _dataclass_to_dict(self)


def _dataclass_to_dict(obj: Any) -> Any:
    """Recursively convert dataclass instances to dictionaries."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _dataclass_to_dict(v) for k, v in obj.__dict__.items()}
    if isinstance(obj, list):
        return [_dataclass_to_dict(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _dataclass_to_dict(v) for k, v in obj.items()}
    return obj
