"""Shared parsing utilities for Shopee data extraction."""

from __future__ import annotations

import re

from shopee_scraper.utils.constants import PRICE_DIVISOR


def parse_price(price_text: str) -> float:
    """
    Parse price from text string.

    Handles Indonesian price format (e.g., "Rp 1.500.000" -> 1500000.0).

    Args:
        price_text: Price string to parse

    Returns:
        Parsed price as float, or 0.0 if parsing fails
    """
    # Remove currency symbols and non-numeric characters except . and ,
    cleaned = re.sub(r"[^\d.,]", "", price_text)
    # Indonesian format: dots as thousand separators, comma as decimal
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def parse_rating(rating_text: str) -> float:
    """
    Parse rating from text string.

    Args:
        rating_text: Rating string (e.g., "4.8", "4,8")

    Returns:
        Parsed rating as float, or 0.0 if parsing fails
    """
    try:
        # Handle both dot and comma as decimal separator
        cleaned = rating_text.strip().replace(",", ".")
        return float(cleaned)
    except (ValueError, AttributeError):
        return 0.0


def parse_sold_count(sold_text: str) -> int:
    """
    Parse sold count from text string.

    Handles formats like "500", "1.2k", "10rb", "1,5jt".

    Args:
        sold_text: Sold count string

    Returns:
        Parsed sold count as integer, or 0 if parsing fails
    """
    if not sold_text:
        return 0

    text = sold_text.lower().strip()

    # Remove common prefixes
    text = re.sub(r"^(terjual|sold)\s*", "", text)

    # Handle Indonesian abbreviations
    multiplier = 1
    if "jt" in text or "juta" in text:
        multiplier = 1_000_000
        text = re.sub(r"(jt|juta)", "", text)
    elif "rb" in text or "ribu" in text:
        multiplier = 1_000
        text = re.sub(r"(rb|ribu)", "", text)
    elif "k" in text:
        multiplier = 1_000
        text = text.replace("k", "")

    # Extract numeric value
    text = text.replace(".", "").replace(",", ".").strip()

    try:
        return int(float(text) * multiplier)
    except (ValueError, AttributeError):
        return 0


def convert_shopee_price(price_value: int | float | None) -> float:
    """
    Convert Shopee internal price format to actual price.

    Shopee stores prices multiplied by PRICE_DIVISOR (100000).

    Args:
        price_value: Raw price value from Shopee API

    Returns:
        Actual price in IDR
    """
    if price_value is None:
        return 0.0
    return float(price_value) / PRICE_DIVISOR


def parse_stock(stock_text: str) -> int:
    """
    Parse stock count from text string.

    Args:
        stock_text: Stock string (e.g., "100", "Stok: 50")

    Returns:
        Parsed stock count as integer, or 0 if parsing fails
    """
    if not stock_text:
        return 0

    # Extract digits only
    digits = re.sub(r"[^\d]", "", stock_text)
    try:
        return int(digits)
    except ValueError:
        return 0
