"""Review endpoints - RESTful resource for product reviews."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query, status

from shopee_scraper.api.dependencies import RequireApiKey, ScraperServiceDep
from shopee_scraper.api.schemas import (
    ErrorResponse,
    ReviewsLinks,
    ReviewsMeta,
    ReviewsResponse,
)


router = APIRouter(prefix="/products", tags=["Reviews"])


@router.get(
    "/{shop_id}/{item_id}/reviews",
    response_model=ReviewsResponse,
    summary="Get product reviews",
    description="Retrieve reviews for a specific product.",
    responses={
        200: {"description": "Product reviews"},
        500: {"model": ErrorResponse, "description": "Scraping error"},
    },
)
async def get_product_reviews(
    service: ScraperServiceDep,
    _api_key: RequireApiKey,
    shop_id: int = Path(..., description="Shop ID", gt=0),
    item_id: int = Path(..., description="Item ID", gt=0),
    max_reviews: int = Query(100, ge=1, le=500, description="Max reviews"),
) -> ReviewsResponse:
    """
    Get reviews for a product.

    Returns paginated reviews with:
    - Rating and comment
    - Author information
    - Review images
    - Likes count
    """
    try:
        result = await service.get_reviews(
            shop_id=shop_id,
            item_id=item_id,
            max_reviews=max_reviews,
        )

        return ReviewsResponse(
            success=True,
            message=f"Found {result['total_count']} reviews",
            meta=ReviewsMeta(
                shop_id=shop_id,
                item_id=item_id,
                total_count=result["total_count"],
            ),
            data=result["reviews"],
            links=ReviewsLinks(
                self=f"/api/v1/products/{shop_id}/{item_id}/reviews",
                product=f"/api/v1/products/{shop_id}/{item_id}",
            ),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e


@router.get(
    "/{shop_id}/{item_id}/reviews/overview",
    summary="Get review overview",
    description="Get aggregated review statistics for a product.",
    responses={
        200: {"description": "Review summary statistics"},
        500: {"model": ErrorResponse, "description": "Scraping error"},
    },
)
async def get_review_summary(
    service: ScraperServiceDep,
    _api_key: RequireApiKey,
    shop_id: int = Path(..., description="Shop ID", gt=0),
    item_id: int = Path(..., description="Item ID", gt=0),
) -> dict[str, Any]:
    """
    Get review summary statistics.

    Returns:
    - Total review count
    - Average rating
    - Rating distribution (1-5 stars)
    """
    try:
        summary = await service.get_review_summary(
            shop_id=shop_id,
            item_id=item_id,
        )

        return {
            "success": True,
            "data": summary,
            "links": {
                "self": f"/api/v1/products/{shop_id}/{item_id}/reviews/overview",
                "reviews": f"/api/v1/products/{shop_id}/{item_id}/reviews",
                "product": f"/api/v1/products/{shop_id}/{item_id}",
            },
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e
