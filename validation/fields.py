"""Validate extracted product fields."""

from __future__ import annotations

import re
from decimal import Decimal

from models import ExtractionFailure, ProductFields

PRICE_ZERO = Decimal("0")
MAX_RATING = 5.0


def validate_product_fields(fields: ProductFields) -> None:
    """Require title + price; rating/reviews are best-effort when present."""
    if not fields.title or len(fields.title.strip()) < 3:
        raise ExtractionFailure("missing or too-short title")

    generic_titles = {
        "amazon.com",
        "best buy",
        "walmart.com",
        "newegg.com",
        "access denied",
    }
    if fields.title.strip().lower() in generic_titles:
        raise ExtractionFailure("generic page title")

    if fields.price is None:
        raise ExtractionFailure("missing price")
    if fields.price <= PRICE_ZERO:
        raise ExtractionFailure(f"nonsensical price: {fields.price}")

    if fields.average_rating is not None:
        if fields.average_rating < 0 or fields.average_rating > MAX_RATING:
            raise ExtractionFailure(f"rating out of range: {fields.average_rating}")

    if fields.review_count is not None and fields.review_count < 0:
        raise ExtractionFailure(f"negative review count: {fields.review_count}")


def is_bot_page(html: str, extra_patterns: list[str] | None = None) -> bool:
    from config import GENERIC_BOT_PATTERNS

    lower = html.lower()
    patterns = list(GENERIC_BOT_PATTERNS)
    if extra_patterns:
        patterns.extend(extra_patterns)
    for pat in patterns:
        if re.search(pat, lower, re.I):
            return True
    return False
