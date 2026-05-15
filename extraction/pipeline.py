"""Sequential extraction fallback pipeline (M1 → M4)."""

from __future__ import annotations

import logging

from extraction.firecrawl_extract import extract_with_firecrawl
from extraction.llm_extract import extract_with_llm
from extraction.playwright_extract import extract_with_playwright
from extraction.requests_bs4 import extract_with_requests
from models import ExtractionFailure, ExtractionMethod, ProductFields, ProductRow
from sites.base import SiteAdapter

logger = logging.getLogger(__name__)


def run_extraction_pipeline(adapter: SiteAdapter, product_url: str) -> ProductRow:
    last_error = "unknown"
    cached_html: str | None = None

    # Method 1: requests + BeautifulSoup
    try:
        fields = extract_with_requests(adapter, product_url)
        return ProductRow.from_fields(adapter.display_name, fields, ExtractionMethod.REQUESTS)
    except ExtractionFailure as e:
        last_error = str(e)
        logger.info("%s M1 failed: %s", adapter.display_name, e)

    # Method 2: Playwright
    try:
        fields, html = extract_with_playwright(adapter, product_url)
        cached_html = html
        return ProductRow.from_fields(adapter.display_name, fields, ExtractionMethod.PLAYWRIGHT)
    except ExtractionFailure as e:
        last_error = str(e)
        logger.info("%s M2 failed: %s", adapter.display_name, e)

    # Method 3: LLM (needs HTML from Playwright if possible)
    if cached_html:
        try:
            fields = extract_with_llm(cached_html, product_url)
            return ProductRow.from_fields(adapter.display_name, fields, ExtractionMethod.LLM)
        except ExtractionFailure as e:
            last_error = str(e)
            logger.info("%s M3 failed: %s", adapter.display_name, e)
    else:
        try:
            from extraction.playwright_extract import fetch_html_playwright

            cached_html = fetch_html_playwright(product_url)
            fields = extract_with_llm(cached_html, product_url)
            return ProductRow.from_fields(adapter.display_name, fields, ExtractionMethod.LLM)
        except ExtractionFailure as e:
            last_error = str(e)
            logger.info("%s M3 failed: %s", adapter.display_name, e)

    # Method 4: Firecrawl
    try:
        fields = extract_with_firecrawl(product_url)
        return ProductRow.from_fields(adapter.display_name, fields, ExtractionMethod.FIRECRAWL)
    except ExtractionFailure as e:
        last_error = str(e)
        logger.info("%s M4 failed: %s", adapter.display_name, e)

    row = ProductRow.failed(adapter.display_name)
    logger.warning("%s all methods failed: %s", adapter.display_name, last_error)
    return row
