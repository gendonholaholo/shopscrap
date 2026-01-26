"""Product endpoints - RESTful resource for products."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import BaseModel, Field

from shopee_scraper.api.dependencies import RequireApiKey, ScraperServiceDep
from shopee_scraper.api.jobs import get_job_queue
from shopee_scraper.api.schemas import ErrorResponse, ProductLinks, SortOrder
from shopee_scraper.exceptions import QueueFullError


router = APIRouter(prefix="/products", tags=["Products"])


# =============================================================================
# Request Schemas
# =============================================================================


class ScrapeListRequest(BaseModel):
    """Request for scraping product list."""

    keyword: str = Field(..., min_length=1, max_length=200)
    max_pages: int = Field(default=1, ge=1, le=10)
    sort_by: SortOrder = SortOrder.RELEVANCY


class ScrapeListAndDetailsRequest(BaseModel):
    """Request for scraping product list with full details."""

    keyword: str = Field(..., min_length=1, max_length=200)
    max_products: int = Field(default=10, ge=1, le=100)
    include_reviews: bool = Field(default=True)


class JobSubmitResponse(BaseModel):
    """Response for async job submission."""

    success: bool = True
    message: str
    data: dict[str, Any]
    links: dict[str, str]


# =============================================================================
# Scraping Endpoints (Async)
# =============================================================================


@router.post(
    "/scrape-list",
    response_model=JobSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Scrape product list by keyword",
    description="Submit an async job to scrape product list from Shopee search results.",
    responses={
        202: {"description": "Job submitted successfully"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def scrape_list(
    request: ScrapeListRequest,
    _api_key: RequireApiKey,
) -> JobSubmitResponse:
    """
    Scrape product list by keyword (async).

    Returns full product details in ExportOutput format:
    - exportedAt, marketplace, count
    - products[] with full details including seller, reviews, variants

    Use GET /jobs/{job_id} to retrieve results when completed.

    - **keyword**: Search keyword (required)
    - **max_pages**: Number of pages to scrape (1-10, default: 1)
    - **sort_by**: Sort order (relevancy, sales, price_asc, price_desc)
    """
    queue = get_job_queue()

    try:
        job = await queue.submit(
            job_type="scrape_list",
            params={
                "keyword": request.keyword,
                "max_pages": request.max_pages,
                "sort_by": request.sort_by.value,
            },
        )
    except QueueFullError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e),
        ) from e

    return JobSubmitResponse(
        success=True,
        message="Scrape job submitted successfully",
        data=job.to_dict(),
        links={
            "self": f"/api/v1/jobs/{job.id}",
            "status": f"/api/v1/jobs/{job.id}/status",
        },
    )


@router.post(
    "/scrape-list-and-details",
    response_model=JobSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Scrape product list with full details",
    description="Submit an async job to scrape products and fetch full details for each.",
    responses={
        202: {"description": "Job submitted successfully"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def scrape_list_and_details(
    request: ScrapeListAndDetailsRequest,
    _api_key: RequireApiKey,
) -> JobSubmitResponse:
    """
    Scrape product list with full details (async).

    Returns ExportOutput format with complete product information:
    - Full product details (images, variants, description)
    - Seller information
    - Reviews (if include_reviews=true)

    - **keyword**: Search keyword (required)
    - **max_products**: Maximum products to scrape (1-100, default: 10)
    - **include_reviews**: Also fetch reviews for each product (default: true)
    """
    queue = get_job_queue()

    try:
        job = await queue.submit(
            job_type="scrape_list_and_details",
            params={
                "keyword": request.keyword,
                "max_products": request.max_products,
                "include_reviews": request.include_reviews,
            },
        )
    except QueueFullError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e),
        ) from e

    return JobSubmitResponse(
        success=True,
        message="Scrape job submitted successfully",
        data=job.to_dict(),
        links={
            "self": f"/api/v1/jobs/{job.id}",
            "status": f"/api/v1/jobs/{job.id}/status",
        },
    )


# =============================================================================
# Direct Resource Access (Sync)
# =============================================================================


@router.get(
    "/{shop_id}/{item_id}",
    summary="Get product detail",
    description="Retrieve detailed information for a specific product in ProductOutput format.",
    responses={
        200: {"description": "Product details in ProductOutput format"},
        404: {"model": ErrorResponse, "description": "Product not found"},
        500: {"model": ErrorResponse, "description": "Scraping error"},
    },
)
async def get_product(
    service: ScraperServiceDep,
    _api_key: RequireApiKey,
    shop_id: int = Path(..., description="Shop ID", gt=0),
    item_id: int = Path(..., description="Item ID", gt=0),
    max_reviews: int = Query(
        default=5, ge=0, le=50, description="Max reviews to fetch"
    ),
) -> dict[str, Any]:
    """
    Get product detail by shop_id and item_id.

    Returns ProductOutput format including:
    - Basic info (id, title, price, stock)
    - Images and variants
    - Seller information
    - Reviews summary and items
    - Category and specifications
    """
    try:
        product = await service.get_product(
            shop_id=shop_id,
            item_id=item_id,
            max_reviews=max_reviews,
        )

        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {shop_id}/{item_id} not found",
            )

        # Add HATEOAS links
        links = ProductLinks(
            self=f"/api/v1/products/{shop_id}/{item_id}",
            reviews=f"/api/v1/products/{shop_id}/{item_id}/reviews",
        )

        return {
            "success": True,
            "data": product,
            "links": links.model_dump(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e
