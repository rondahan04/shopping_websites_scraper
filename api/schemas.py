"""API request/response models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from models import ProductRow, row_has_scraped_price


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    rescrape_price_gaps: bool = True


class JobStartRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    rescrape_price_gaps: bool = True


class JobStartResponse(BaseModel):
    job_id: str


class JobProgressOut(BaseModel):
    percent: int
    message: str
    stores_done: list[str]
    stores_total: int


class JobStatusResponse(BaseModel):
    job_id: str
    query: str
    status: str
    progress: JobProgressOut
    result: SearchResponse | None = None
    error: str | None = None


class ProductRowOut(BaseModel):
    website: str
    product_title: str
    price: str
    average_rating: str
    review_count: str
    status: str
    method: str
    source_url: str
    has_price: bool


class SearchResponse(BaseModel):
    query: str
    rows: list[ProductRowOut]
    success_count: int
    total_sites: int


def row_to_api(row: ProductRow) -> ProductRowOut:
    return ProductRowOut(
        website=row.website,
        product_title=row.product_title,
        price=row.price,
        average_rating=row.average_rating,
        review_count=row.review_count,
        status=row.status,
        method=row.method,
        source_url=row.source_url,
        has_price=row_has_scraped_price(row),
    )


def build_search_response(query: str, rows: list[ProductRow]) -> SearchResponse:
    api_rows = [row_to_api(r) for r in rows]
    success = sum(1 for r in rows if row_has_scraped_price(r))
    return SearchResponse(
        query=query,
        rows=api_rows,
        success_count=success,
        total_sites=len(rows),
    )
