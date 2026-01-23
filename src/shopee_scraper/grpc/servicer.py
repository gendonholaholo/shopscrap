"""gRPC service implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from shopee_scraper import __version__
from shopee_scraper.services.scraper_service import ScraperService
from shopee_scraper.utils.logging import get_logger


if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from shopee_scraper.grpc import shopee_pb2

logger = get_logger(__name__)


class ShopeeScraperServicer:
    """
    gRPC servicer implementation for Shopee Scraper.

    This class implements the ShopeeScraperService defined in shopee.proto.
    It uses ScraperService for business logic (shared with REST API).
    """

    def __init__(self) -> None:
        """Initialize servicer with scraper service."""
        self._service = ScraperService(headless=True)

    async def HealthCheck(
        self,
        request: shopee_pb2.HealthRequest,
        context: object,
    ) -> shopee_pb2.HealthResponse:
        """Health check endpoint."""
        from shopee_scraper.grpc import shopee_pb2

        health = await self._service.health_check()

        return shopee_pb2.HealthResponse(
            status=health["status"],
            version=__version__,
            scraper_ready=health["scraper_initialized"],
        )

    async def SearchProducts(
        self,
        request: shopee_pb2.SearchRequest,
        context: object,
    ) -> shopee_pb2.SearchResponse:
        """Search products by keyword."""
        from shopee_scraper.grpc import shopee_pb2

        logger.info(f"gRPC: SearchProducts for '{request.keyword}'")

        sort_map = {
            0: "relevancy",
            1: "sales",
            2: "price_asc",
            3: "price_desc",
        }

        result = await self._service.search_products(
            keyword=request.keyword,
            max_pages=request.max_pages or 1,
            sort_by=sort_map.get(request.sort_by, "relevancy"),
            save=request.save,
        )

        products = [self._dict_to_product(p) for p in result["products"]]

        return shopee_pb2.SearchResponse(
            success=True,
            message=f"Found {result['total_count']} products",
            meta=shopee_pb2.SearchMeta(
                keyword=result["keyword"],
                total_count=result["total_count"],
                page_count=result["page_count"],
                sort_by=result["sort_by"],
            ),
            products=products,
        )

    async def SearchProductsStream(
        self,
        request: shopee_pb2.SearchRequest,
        context: object,
    ) -> AsyncIterator[shopee_pb2.Product]:
        """Stream search results for large datasets."""
        logger.info(f"gRPC: SearchProductsStream for '{request.keyword}'")

        sort_map = {
            0: "relevancy",
            1: "sales",
            2: "price_asc",
            3: "price_desc",
        }

        result = await self._service.search_products(
            keyword=request.keyword,
            max_pages=request.max_pages or 1,
            sort_by=sort_map.get(request.sort_by, "relevancy"),
            save=request.save,
        )

        for product_dict in result["products"]:
            yield self._dict_to_product(product_dict)

    async def GetProduct(
        self,
        request: shopee_pb2.ProductRequest,
        context: object,
    ) -> shopee_pb2.ProductResponse:
        """Get product detail."""
        from shopee_scraper.grpc import shopee_pb2

        logger.info(f"gRPC: GetProduct {request.shop_id}/{request.item_id}")

        product = await self._service.get_product(
            shop_id=request.shop_id,
            item_id=request.item_id,
            save=request.save,
        )

        if not product:
            return shopee_pb2.ProductResponse(
                success=False,
                message="Product not found",
            )

        return shopee_pb2.ProductResponse(
            success=True,
            message="OK",
            product=self._dict_to_product(product),
        )

    async def GetReviews(
        self,
        request: shopee_pb2.ReviewsRequest,
        context: object,
    ) -> shopee_pb2.ReviewsResponse:
        """Get product reviews."""
        from shopee_scraper.grpc import shopee_pb2

        logger.info(f"gRPC: GetReviews {request.shop_id}/{request.item_id}")

        result = await self._service.get_reviews(
            shop_id=request.shop_id,
            item_id=request.item_id,
            max_reviews=request.max_reviews or 100,
            save=request.save,
        )

        reviews = [self._dict_to_review(r) for r in result["reviews"]]

        return shopee_pb2.ReviewsResponse(
            success=True,
            message=f"Found {result['total_count']} reviews",
            meta=shopee_pb2.ReviewsMeta(
                shop_id=request.shop_id,
                item_id=request.item_id,
                total_count=result["total_count"],
            ),
            reviews=reviews,
        )

    async def GetReviewSummary(
        self,
        request: shopee_pb2.ReviewsRequest,
        context: object,
    ) -> shopee_pb2.ReviewSummaryResponse:
        """Get review summary."""
        from shopee_scraper.grpc import shopee_pb2

        logger.info(f"gRPC: GetReviewSummary {request.shop_id}/{request.item_id}")

        summary = await self._service.get_review_summary(
            shop_id=request.shop_id,
            item_id=request.item_id,
        )

        return shopee_pb2.ReviewSummaryResponse(
            success=True,
            total_reviews=summary.get("total_reviews", 0),
            average_rating=summary.get("average_rating", 0.0),
            rating_distribution=summary.get("rating_distribution", {}),
        )

    async def close(self) -> None:
        """Cleanup resources."""
        await self._service.close()

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _dict_to_product(self, data: dict) -> shopee_pb2.Product:
        """Convert dict to Product protobuf message."""
        from shopee_scraper.grpc import shopee_pb2

        return shopee_pb2.Product(
            item_id=data.get("item_id", 0),
            shop_id=data.get("shop_id", 0),
            name=data.get("name", ""),
            price=data.get("price", 0.0),
            original_price=data.get("original_price", 0.0),
            discount=data.get("discount", 0.0),
            sold=data.get("sold", 0),
            stock=data.get("stock", 0),
            rating=data.get("rating", 0.0),
            rating_count=data.get("rating_count", 0),
            image_url=data.get("image_url", ""),
            shop_name=data.get("shop_name", ""),
            location=data.get("location", ""),
            description=data.get("description", ""),
            categories=data.get("categories", []),
            images=data.get("images", []),
        )

    def _dict_to_review(self, data: dict) -> shopee_pb2.Review:
        """Convert dict to Review protobuf message."""
        from shopee_scraper.grpc import shopee_pb2

        author_data = data.get("author", {})
        author = shopee_pb2.ReviewAuthor(
            user_id=author_data.get("user_id", 0),
            username=author_data.get("username", ""),
            avatar=author_data.get("avatar", ""),
        )

        return shopee_pb2.Review(
            rating=data.get("rating", 0),
            comment=data.get("comment", ""),
            author=author,
            created_at=data.get("created_at", ""),
            images=data.get("images", []),
            likes=data.get("likes", 0),
        )
