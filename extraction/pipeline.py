"""Sequential extraction fallback pipeline (M1 → M4)."""

from __future__ import annotations

import logging

from extraction.firecrawl_extract import extract_with_firecrawl
from extraction.llm_extract import extract_with_llm
from extraction.playwright_extract import extract_with_playwright
from extraction.scrapling_extract import extract_with_scrapling
from models import ExtractionFailure, ExtractionMethod, ProductRow
from sites.base import SiteAdapter
from validation.fields import validate_product_fields

logger = logging.getLogger(__name__)


def run_extraction_pipeline(
    adapter: SiteAdapter,
    product_url: str,
    *,
    capture_product_html: bool = False,
) -> tuple[ProductRow, str | None]:
    """Return ``(row, product_html)``; ``product_html`` is set when extraction succeeds and capture is on."""
    last_error = "unknown"
    cached_html: str | None = None

    # Method 1: Scrapling + BeautifulSoup
    try:
        fields, html = extract_with_scrapling(adapter, product_url)
        row = ProductRow.from_fields(
            adapter.display_name, fields, ExtractionMethod.SCRAPLING, source_url=product_url
        )
        return row, html if capture_product_html else None
    except ExtractionFailure as e:
        last_error = str(e)
        logger.info("%s M1 failed: %s", adapter.display_name, e)

    # Method 2: Playwright
    try:
        fields, html = extract_with_playwright(adapter, product_url)
        cached_html = html
        row = ProductRow.from_fields(
            adapter.display_name, fields, ExtractionMethod.PLAYWRIGHT, source_url=product_url
        )
        return row, html if capture_product_html else None
    except ExtractionFailure as e:
        last_error = str(e)
        logger.info("%s M2 failed: %s", adapter.display_name, e)

    # Method 3: LLM (needs HTML from Playwright if possible)
    if cached_html:
        try:
            fields = extract_with_llm(cached_html, product_url)
            row = ProductRow.from_fields(
                adapter.display_name, fields, ExtractionMethod.LLM, source_url=product_url
            )
            return row, cached_html if capture_product_html else None
        except ExtractionFailure as e:
            last_error = str(e)
            logger.info("%s M3 failed: %s", adapter.display_name, e)
    else:
        try:
            from extraction.playwright_extract import fetch_html_playwright

            cached_html = fetch_html_playwright(product_url)
            fields = extract_with_llm(cached_html, product_url)
            row = ProductRow.from_fields(
                adapter.display_name, fields, ExtractionMethod.LLM, source_url=product_url
            )
            return row, cached_html if capture_product_html else None
        except ExtractionFailure as e:
            last_error = str(e)
            logger.info("%s M3 failed: %s", adapter.display_name, e)

    # Method 4: Firecrawl (no raw HTML returned here; use SERP snapshot or Firecrawl logs if needed)
    try:
        fields = extract_with_firecrawl(product_url)
        row = ProductRow.from_fields(
            adapter.display_name, fields, ExtractionMethod.FIRECRAWL, source_url=product_url
        )
        return row, None
    except ExtractionFailure as e:
        last_error = str(e)
        logger.info("%s M4 failed: %s", adapter.display_name, e)

    # Out-of-stock PDPs may yield a title via LLM/Firecrawl but no price.
    if not cached_html:
        try:
            from extraction.firecrawl_extract import fetch_html_firecrawl

            cached_html = fetch_html_firecrawl(product_url, wait_ms=6_000)
        except ExtractionFailure:
            pass

    if cached_html:
        try:
            fields = extract_with_llm(cached_html, product_url)
            validate_product_fields(fields, require_price=False)
            if fields.title and fields.price is None:
                row = ProductRow.from_fields(
                    adapter.display_name,
                    fields,
                    ExtractionMethod.LLM,
                    source_url=product_url,
                )
                logger.info(
                    "%s accepted title-only (out of stock / no price on page)",
                    adapter.display_name,
                )
                return row, cached_html if capture_product_html else None
        except ExtractionFailure:
            pass

    row = ProductRow.failed(adapter.display_name)
    logger.warning("%s all methods failed: %s", adapter.display_name, last_error)
    return row, None
