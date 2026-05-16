"""Sequential extraction fallback pipeline (M1 → M4) with optional US-geo price retry."""

from __future__ import annotations

import logging

from config import SETTINGS
from extraction.firecrawl_extract import extract_with_firecrawl
from extraction.llm_extract import extract_with_llm
from extraction.playwright_extract import extract_with_playwright
from extraction.scrapling_extract import extract_with_http
from models import ExtractionFailure, ExtractionMethod, ProductRow, row_has_scraped_price
from sites.base import SiteAdapter

logger = logging.getLogger(__name__)


def _row_has_price(row: ProductRow) -> bool:
    return row_has_scraped_price(row)


def _run_core_pipeline(
    adapter: SiteAdapter,
    product_url: str,
    *,
    capture_product_html: bool,
    proxy_url: str | None,
) -> tuple[ProductRow, str | None, str | None]:
    """M1–M4 with optional proxy. Returns (row, product_html, cached_html_for_llm)."""
    last_error = "unknown"
    cached_html: str | None = None

    try:
        fields, html = extract_with_http(adapter, product_url, proxy_url=proxy_url)
        row = ProductRow.from_fields(
            adapter.display_name, fields, ExtractionMethod.HTTP, source_url=product_url
        )
        return row, html if capture_product_html else None, html
    except ExtractionFailure as e:
        last_error = str(e)
        logger.info("%s M1 failed: %s", adapter.display_name, e)

    try:
        fields, html = extract_with_playwright(adapter, product_url, proxy_url=proxy_url)
        cached_html = html
        row = ProductRow.from_fields(
            adapter.display_name, fields, ExtractionMethod.PLAYWRIGHT, source_url=product_url
        )
        return row, html if capture_product_html else None, cached_html
    except ExtractionFailure as e:
        last_error = str(e)
        logger.info("%s M2 failed: %s", adapter.display_name, e)

    if cached_html:
        try:
            fields = extract_with_llm(cached_html, product_url)
            row = ProductRow.from_fields(
                adapter.display_name, fields, ExtractionMethod.LLM, source_url=product_url
            )
            return row, cached_html if capture_product_html else None, cached_html
        except ExtractionFailure as e:
            last_error = str(e)
            logger.info("%s M3 failed: %s", adapter.display_name, e)
    else:
        try:
            from extraction.playwright_extract import fetch_html_playwright

            cached_html = fetch_html_playwright(product_url, proxy_url=proxy_url)
            fields = extract_with_llm(cached_html, product_url)
            row = ProductRow.from_fields(
                adapter.display_name, fields, ExtractionMethod.LLM, source_url=product_url
            )
            return row, cached_html if capture_product_html else None, cached_html
        except ExtractionFailure as e:
            last_error = str(e)
            logger.info("%s M3 failed: %s", adapter.display_name, e)

    try:
        fields = extract_with_firecrawl(product_url)
        row = ProductRow.from_fields(
            adapter.display_name, fields, ExtractionMethod.FIRECRAWL, source_url=product_url
        )
        return row, None, cached_html
    except ExtractionFailure as e:
        last_error = str(e)
        logger.info("%s M4 failed: %s", adapter.display_name, e)

    if not cached_html:
        try:
            from extraction.firecrawl_extract import fetch_html_firecrawl

            cached_html = fetch_html_firecrawl(product_url, wait_ms=6_000)
        except ExtractionFailure:
            pass

    row = ProductRow.failed(adapter.display_name)
    logger.warning("%s all methods failed: %s", adapter.display_name, last_error)
    return row, None, cached_html


def _retry_usa_geo_for_price(
    adapter: SiteAdapter,
    product_url: str,
    *,
    capture_product_html: bool,
) -> tuple[ProductRow, str | None] | None:
    proxy = SETTINGS.usa_http_proxy
    if not proxy or not SETTINGS.usa_geo_retry_enabled:
        return None

    logger.info(
        "%s retrying PDP via USA proxy for price (geo may hide pricing outside US)",
        adapter.display_name,
    )
    row, html, _ = _run_core_pipeline(
        adapter,
        product_url,
        capture_product_html=capture_product_html,
        proxy_url=proxy,
    )
    if _row_has_price(row):
        if row.method == ExtractionMethod.HTTP.value:
            row = ProductRow(
                website=row.website,
                product_title=row.product_title,
                price=row.price,
                average_rating=row.average_rating,
                review_count=row.review_count,
                status=row.status,
                method=f"{row.method}+usa",
                source_url=row.source_url,
                serp_html_path=row.serp_html_path,
                product_html_path=row.product_html_path,
            )
        return row, html
    return None


def run_extraction_pipeline(
    adapter: SiteAdapter,
    product_url: str,
    *,
    capture_product_html: bool = False,
) -> tuple[ProductRow, str | None]:
    """Return ``(row, product_html)``; retries through US proxy when price is missing."""
    row, html, _ = _run_core_pipeline(
        adapter,
        product_url,
        capture_product_html=capture_product_html,
        proxy_url=None,
    )
    if _row_has_price(row):
        return row, html

    if row.status == "Success" and row.price == "N/A":
        retry = _retry_usa_geo_for_price(
            adapter, product_url, capture_product_html=capture_product_html
        )
        if retry:
            return retry

    if row.status == "Failed":
        retry = _retry_usa_geo_for_price(
            adapter, product_url, capture_product_html=capture_product_html
        )
        if retry:
            return retry

    return row, html
