"""Transform raw extractor data into standardized output format."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from shopee_scraper.models.output import (
    CategoryInfo,
    ExportOutput,
    LabelsInfo,
    ProductOutput,
    ReviewerInfo,
    ReviewInfo,
    ReviewsInfo,
    SellerInfo,
    ShippingInfo,
    SpecsInfo,
    VariantInfo,
    VariantOption,
)
from shopee_scraper.utils.constants import BASE_URL


SCRAPE_VERSION = "1.0.0"


def transform_product(
    product_data: dict[str, Any],
    reviews_data: list[dict[str, Any]] | None = None,
) -> ProductOutput:
    """
    Transform raw product and review data into ProductOutput format.

    Args:
        product_data: Raw product data from ProductExtractor
        reviews_data: Raw review data from ReviewExtractor (optional)

    Returns:
        ProductOutput instance
    """
    shop = product_data.get("shop", {})
    shop_id = product_data.get("shop_id", 0)
    item_id = product_data.get("item_id", 0)

    # Build seller info
    seller = SellerInfo(
        id=str(shop.get("shop_id", shop_id)),
        name=shop.get("name", ""),
        url=f"{BASE_URL}/shop/{shop.get('username', '')}",
        location=shop.get("location", ""),
        isOfficialStore=shop.get("is_official", False),
    )

    # Build category info
    category_path = product_data.get("category_path", [])
    category = CategoryInfo(
        id=str(product_data.get("category_id", "")),
        name=category_path[-1] if category_path else "",
        breadcrumb=category_path,
    )

    # Build specifications
    attributes = product_data.get("attributes", [])
    custom_specs = {}
    for attr in attributes:
        if isinstance(attr, dict):
            name = attr.get("name", "")
            value = attr.get("value", "")
            if name and value:
                custom_specs[name] = value

    specs = SpecsInfo(
        condition=product_data.get("condition", "new"),
        minOrder=1,
        weight=0,
        sku=None,
        customSpecs=custom_specs,
    )

    # Build variants from tier_variations
    variants = _transform_variants(product_data)

    # Build shipping info
    shipping = ShippingInfo(
        freeShipping=False,
        insuranceRequired=False,
    )

    # Build reviews info
    reviews = _transform_reviews(product_data, reviews_data)

    # Build labels
    labels = LabelsInfo(
        isCOD=False,
        isWholesale=False,
        isCashback=False,
    )

    # Get images
    images = product_data.get("images", [])
    thumbnail = images[0] + "~thumb.jpeg" if images else ""

    # Get price (convert from float to int), guard against None
    price = int(product_data.get("price") or 0)
    stock = product_data.get("stock") or 0

    return ProductOutput(
        id=str(item_id),
        url=product_data.get("url", f"{BASE_URL}/product/{shop_id}/{item_id}"),
        marketplace="shopee",
        title=product_data.get("name", ""),
        price=price,
        thumbnail=thumbnail,
        images=images,
        seller=seller,
        rating=product_data.get("rating") or 0.0,
        reviewCount=product_data.get("rating_count") or 0,
        soldCount=product_data.get("sold") or 0,
        stock=stock,
        isAvailable=stock > 0,
        description=product_data.get("description", ""),
        descriptionHtml=_text_to_html(product_data.get("description", "")),
        category=category,
        specifications=specs,
        variants=variants,
        shipping=shipping,
        reviews=reviews,
        labels=labels,
        scrapedAt=datetime.now().isoformat() + "Z",
        scrapeVersion=SCRAPE_VERSION,
    )


def _transform_variants(product_data: dict[str, Any]) -> list[VariantInfo]:
    """Transform tier_variations and models into VariantInfo list."""
    variants = []
    tier_variations = product_data.get("variations", [])
    models = product_data.get("variants", [])

    for tier in tier_variations:
        tier_name = tier.get("name", "")
        tier_options = tier.get("options", [])

        options = []
        for opt_name in tier_options:
            # Find matching model for price/stock
            matching_model = None
            for model in models:
                if opt_name in model.get("name", ""):
                    matching_model = model
                    break

            price = int(matching_model.get("price") or 0) if matching_model else 0
            stock = (matching_model.get("stock") or 0) if matching_model else 0

            options.append(
                VariantOption(
                    name=opt_name,
                    price=price,
                    stock=stock,
                    isActive=stock > 0,
                )
            )

        if tier_name and options:
            variants.append(VariantInfo(name=tier_name, options=options))

    return variants


def _transform_reviews(
    product_data: dict[str, Any],
    reviews_data: list[dict[str, Any]] | None,
) -> ReviewsInfo:
    """Transform reviews data into ReviewsInfo."""
    rating = product_data.get("rating", 0.0)
    count = product_data.get("rating_count", 0)
    rating_breakdown = product_data.get("rating_breakdown", [])

    # Build breakdown dict
    breakdown = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    if isinstance(rating_breakdown, list) and len(rating_breakdown) >= 5:
        for i in range(5):
            breakdown[str(i + 1)] = (
                rating_breakdown[i] if i < len(rating_breakdown) else 0
            )

    # Transform review items
    items = []
    with_photos = 0
    with_description = 0

    if reviews_data:
        for raw in reviews_data:
            review = _transform_review_item(raw)
            if review:
                items.append(review)
                if review.images:
                    with_photos += 1
                if review.content:
                    with_description += 1

    return ReviewsInfo(
        rating=rating,
        count=count,
        breakdown=breakdown,
        withPhotos=with_photos,
        withDescription=with_description,
        items=items,
    )


def _transform_review_item(raw: dict[str, Any]) -> ReviewInfo | None:
    """Transform a single review into ReviewInfo."""
    if not raw:
        return None

    author = raw.get("author", {})
    reviewer = ReviewerInfo(
        id=str(author.get("user_id", "")),
        username=author.get("username", ""),
        displayName=author.get("username", ""),
        avatarUrl=author.get("avatar", ""),
        isVerifiedPurchase=not raw.get("is_anonymous", False),
        memberSince="",
        totalReviews=0,
        helpfulVotes=0,
    )

    return ReviewInfo(
        id=str(raw.get("rating_id", "")),
        reviewer=reviewer,
        rating=raw.get("rating", 0),
        title="",
        content=raw.get("comment", ""),
        images=raw.get("images", []),
        videos=raw.get("videos", []),
        variantPurchased=raw.get("variation", ""),
        purchaseDate="",
        reviewDate=raw.get("created_at", ""),
        isEdited=False,
        helpfulCount=raw.get("likes", 0),
        replyFromSeller=raw.get("shop_reply") or None,
        replyDate=None,
    )


def _text_to_html(text: str) -> str:
    """Convert plain text to simple HTML."""
    if not text:
        return ""
    lines = text.split("\n")
    html_lines = [f"<p>{line}</p>" if line.strip() else "<br>" for line in lines]
    return "".join(html_lines)


def create_export(products: list[ProductOutput]) -> ExportOutput:
    """
    Create ExportOutput wrapper for a list of products.

    Args:
        products: List of ProductOutput instances

    Returns:
        ExportOutput instance
    """
    return ExportOutput(
        exportedAt=datetime.now().isoformat() + "Z",
        marketplace="shopee",
        count=len(products),
        products=products,
    )
