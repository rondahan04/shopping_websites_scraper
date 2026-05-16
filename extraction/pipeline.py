"""Product PDP extraction: four-stage fallback pipeline.

Stage 1 — Basic scraping
    HTTP GET (httpx) + BeautifulSoup parsers on each site's adapter.

Stage 2 — Browser-based scraping
    Playwright loads the page like a real browser; HTML is parsed with BeautifulSoup.

Stage 3 — LLM-based extraction
    Visible page text from prior HTML is sent to an LLM for structured fields.

Stage 4 — Firecrawl
    Firecrawl API fetches or extracts the page when local methods fail.

Each stage is attempted in order; the first successful extraction wins.
"""

from __future__ import annotations

import logging

from extraction.firecrawl_extract import extract_with_firecrawl
from extraction.llm_extract import extract_with_llm
from extraction.playwright_extract import extract_with_playwright
from extraction.scrapling_extract import extract_with_http
from models import ExtractionFailure, ExtractionMethod, ProductRow, row_has_scraped_price
from sites.base import SiteAdapter

logger = logging.getLogger(__name__)

_STAGE_LABELS = (
    "basic (HTTP + BeautifulSoup)",
    "browser (Playwright)",
    "LLM extraction",
    "Firecrawl API",
)


def _row_has_price(row: ProductRow) -> bool:
    return row_has_scraped_price(row)


def _run_core_pipeline(
    adapter: SiteAdapter,
    product_url: str,
    *,
    capture_product_html: bool,
    skip_http: bool = False,
) -> tuple[ProductRow, str | None, str | None]:
    """Run stages 1→4 in order. Returns (row, product_html, cached_html_for_llm)."""
    last_error = "unknown"
    cached_html: str | None = None

    # Stage 1: basic scraping
    if not skip_http:
        try:
            fields, html = extract_with_http(adapter, product_url)
            row = ProductRow.from_fields(
                adapter.display_name, fields, ExtractionMethod.HTTP, source_url=product_url
            )
            logger.info("%s PDP via stage 1 %s", adapter.display_name, _STAGE_LABELS[0])
            return row, html if capture_product_html else None, html
        except ExtractionFailure as e:
            last_error = str(e)
            logger.info("%s stage 1 failed: %s", adapter.display_name, e)

    # Stage 2: browser-based scraping
    try:
        fields, html = extract_with_playwright(adapter, product_url)
        cached_html = html
        row = ProductRow.from_fields(
            adapter.display_name, fields, ExtractionMethod.PLAYWRIGHT, source_url=product_url
        )
        logger.info("%s PDP via stage 2 %s", adapter.display_name, _STAGE_LABELS[1])
        return row, html if capture_product_html else None, cached_html
    except ExtractionFailure as e:
        last_error = str(e)
        logger.info("%s stage 2 failed: %s", adapter.display_name, e)

    # Stage 3: LLM-based extraction (reuse Playwright HTML when available)
    if cached_html:
        try:
            fields = extract_with_llm(cached_html, product_url)
            row = ProductRow.from_fields(
                adapter.display_name, fields, ExtractionMethod.LLM, source_url=product_url
            )
            logger.info("%s PDP via stage 3 %s", adapter.display_name, _STAGE_LABELS[2])
            return row, cached_html if capture_product_html else None, cached_html
        except ExtractionFailure as e:
            last_error = str(e)
            logger.info("%s stage 3 failed: %s", adapter.display_name, e)
    else:
        try:
            from extraction.playwright_extract import fetch_html_playwright

            cached_html = fetch_html_playwright(product_url)
            fields = extract_with_llm(cached_html, product_url)
            row = ProductRow.from_fields(
                adapter.display_name, fields, ExtractionMethod.LLM, source_url=product_url
            )
            logger.info("%s PDP via stage 3 %s", adapter.display_name, _STAGE_LABELS[2])
            return row, cached_html if capture_product_html else None, cached_html
        except ExtractionFailure as e:
            last_error = str(e)
            logger.info("%s stage 3 failed: %s", adapter.display_name, e)

    # Stage 4: Firecrawl API
    try:
        fields = extract_with_firecrawl(product_url)
        row = ProductRow.from_fields(
            adapter.display_name, fields, ExtractionMethod.FIRECRAWL, source_url=product_url
        )
        logger.info("%s PDP via stage 4 %s", adapter.display_name, _STAGE_LABELS[3])
        return row, None, cached_html
    except ExtractionFailure as e:
        last_error = str(e)
        logger.info("%s stage 4 failed: %s", adapter.display_name, e)

    row = ProductRow.failed(adapter.display_name)
    logger.warning("%s all pipeline stages failed: %s", adapter.display_name, last_error)
    return row, None, cached_html


def run_extraction_pipeline_price_retry(
    adapter: SiteAdapter,
    product_url: str,
    *,
    capture_product_html: bool = False,
) -> tuple[ProductRow, str | None]:
    """Re-run stages 2→4 after LLM price verify rejected stage 1."""
    logger.info(
        "%s retrying PDP pipeline after price reject (stages 2–4)",
        adapter.display_name,
    )
    row, html, _ = _run_core_pipeline(
        adapter,
        product_url,
        capture_product_html=capture_product_html,
        skip_http=True,
    )
    return row, html


def run_extraction_pipeline(
    adapter: SiteAdapter,
    product_url: str,
    *,
    capture_product_html: bool = False,
) -> tuple[ProductRow, str | None]:
    """Return ``(row, product_html)`` using the four-stage PDP pipeline."""
    row, html, _ = _run_core_pipeline(
        adapter,
        product_url,
        capture_product_html=capture_product_html,
    )
    return row, html
