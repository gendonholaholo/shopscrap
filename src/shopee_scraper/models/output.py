"""Output data models - re-exports from api/schemas.py for backwards compatibility.

All models are now Pydantic BaseModel classes from api/schemas.py.
The type aliases maintain backwards compatibility with existing code.
"""

from __future__ import annotations

from typing import Any

# Re-export all models from api/schemas with aliases for backwards compatibility
from shopee_scraper.api.schemas import (
    CategorySchema as CategoryInfo,
)
from shopee_scraper.api.schemas import (
    ExportSchema as ExportOutput,
)
from shopee_scraper.api.schemas import (
    LabelsSchema as LabelsInfo,
)
from shopee_scraper.api.schemas import (
    ProductSchema as ProductOutput,
)
from shopee_scraper.api.schemas import (
    ReviewerSchema as ReviewerInfo,
)
from shopee_scraper.api.schemas import (
    ReviewItemSchema as ReviewInfo,
)
from shopee_scraper.api.schemas import (
    ReviewsSchema as ReviewsInfo,
)
from shopee_scraper.api.schemas import (
    SellerSchema as SellerInfo,
)
from shopee_scraper.api.schemas import (
    ShippingSchema as ShippingInfo,
)
from shopee_scraper.api.schemas import (
    SpecsSchema as SpecsInfo,
)
from shopee_scraper.api.schemas import (
    VariantOptionSchema as VariantOption,
)
from shopee_scraper.api.schemas import (
    VariantSchema as VariantInfo,
)


__all__ = [
    "CategoryInfo",
    "ExportOutput",
    "LabelsInfo",
    "ProductOutput",
    "ReviewInfo",
    "ReviewerInfo",
    "ReviewsInfo",
    "SellerInfo",
    "ShippingInfo",
    "SpecsInfo",
    "VariantInfo",
    "VariantOption",
    "to_dict",
]


def to_dict(obj: Any) -> Any:
    """Convert Pydantic model or nested structure to dictionary.

    This replaces the old _dataclass_to_dict function.
    Pydantic models use model_dump() instead.
    """
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, list):
        return [to_dict(item) for item in obj]
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    return obj


# Backwards compatibility alias
_dataclass_to_dict = to_dict
