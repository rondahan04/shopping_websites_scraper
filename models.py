"""Shared data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Literal


class ExtractionMethod(str, Enum):
    REQUESTS = "requests"
    PLAYWRIGHT = "playwright"
    LLM = "llm"
    FIRECRAWL = "firecrawl"
    NA = "N/A"


Status = Literal["Success", "Failed"]


@dataclass
class SearchResult:
    title: str
    url: str
    rank: int


@dataclass
class ProductFields:
    title: str
    price: Decimal | None
    average_rating: float | None
    review_count: int | None


@dataclass
class ProductRow:
    website: str
    product_title: str = "N/A"
    price: str = "N/A"
    average_rating: str = "N/A"
    review_count: str = "N/A"
    status: Status = "Failed"
    method: str = "N/A"

    @classmethod
    def failed(cls, website: str) -> ProductRow:
        return cls(website=website, status="Failed", method="N/A")

    @classmethod
    def from_fields(
        cls,
        website: str,
        fields: ProductFields,
        method: ExtractionMethod,
    ) -> ProductRow:
        price_str = "N/A"
        if fields.price is not None:
            price_str = f"${fields.price:,.2f}"

        rating_str = "N/A"
        if fields.average_rating is not None:
            rating_str = f"{fields.average_rating:.1f}"

        reviews_str = "N/A"
        if fields.review_count is not None:
            reviews_str = f"{fields.review_count:,}"

        return cls(
            website=website,
            product_title=fields.title,
            price=price_str,
            average_rating=rating_str,
            review_count=reviews_str,
            status="Success",
            method=method.value,
        )


@dataclass
class ExtractionFailure(Exception):
    reason: str
    method: ExtractionMethod | None = None

    def __str__(self) -> str:
        return self.reason


@dataclass
class MatchCandidate:
    result: SearchResult
    score: float
    details: dict = field(default_factory=dict)
