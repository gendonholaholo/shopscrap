"""SQLAlchemy models for scrape logging."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, Float, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSON, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ScrapeProduct(Base):
    """Logged product from a scrape operation."""

    __tablename__ = "scrape_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    shop_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[float] = mapped_column(Float, default=0.0)
    price_min: Mapped[float] = mapped_column(Float, default=0.0)
    price_max: Mapped[float] = mapped_column(Float, default=0.0)
    price_before_discount: Mapped[float] = mapped_column(Float, default=0.0)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    sold: Mapped[int] = mapped_column(Integer, default=0)
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    images: Mapped[dict | list] = mapped_column(JSON, default=list)
    variants: Mapped[dict | list] = mapped_column(JSON, default=list)
    variations: Mapped[dict | list] = mapped_column(JSON, default=list)
    category_id: Mapped[int] = mapped_column(BigInteger, default=0)
    category_path: Mapped[dict | list] = mapped_column(JSON, default=list)
    condition: Mapped[str] = mapped_column(Text, default="new")
    shop_name: Mapped[str] = mapped_column(Text, default="")
    shop_username: Mapped[str] = mapped_column(Text, default="")
    shop_location: Mapped[str] = mapped_column(Text, default="")
    shop_rating: Mapped[float] = mapped_column(Float, default=0.0)
    shop_is_official: Mapped[bool] = mapped_column(Boolean, default=False)
    attributes: Mapped[dict | list] = mapped_column(JSON, default=list)
    url: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(Text, default="")
    api_format: Mapped[str] = mapped_column(Text, default="")
    raw_top_keys: Mapped[dict | list] = mapped_column(JSON, nullable=True)
    job_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_scrape_products_item_id", "item_id"),
        Index("ix_scrape_products_scraped_at", "scraped_at"),
    )
