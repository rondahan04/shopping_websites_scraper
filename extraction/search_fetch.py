"""Search-page fetch: same four-stage pipeline as PDP extraction."""

from __future__ import annotations

import logging

from config import SETTINGS
from extraction.firecrawl_extract import fetch_html_firecrawl
from extraction.llm_extract import parse_serp_with_llm
from extraction.serp_fallback import firecrawl_extract_serp
from extraction.playwright_extract import fetch_html_playwright
from models import ExtractionFailure, SearchResult
from sites.base import SiteAdapter
from utils.http_fetch import fetch_html_http
from validation.fields import is_bot_page

logger = logging.getLogger(__name__)


def _parse_serp(adapter: SiteAdapter, html: str, search_url: str) -> list[SearchResult]:
    if is_bot_page(html, adapter.bot_check_patterns()):
        return []
    results = adapter.parse_search_results(html, search_url)
    if results:
        return results
    if adapter.domain == "bestbuy.com":
        from sites.bestbuy import salvage_bestbuy_serp_links

        return salvage_bestbuy_serp_links(html, search_url)
    if adapter.domain == "newegg.com":
        from sites.newegg import salvage_newegg_serp_links

        return salvage_newegg_serp_links(html, search_url)
    return []


def fetch_search_results(
    adapter: SiteAdapter,
    search_url: str,
    *,
    query: str = "",
) -> tuple[list[SearchResult], str | None]:
    """Fetch SERP using stage 1 → 2 → 3 → 4 (same order as PDP pipeline).

    Returns ``(results, serp_html)`` where ``serp_html`` is the document that produced
    ``results`` when non-empty; otherwise the last HTML fetched for forensics, or ``None``.
    """
    patterns = adapter.bot_check_patterns()
    cached_html: str | None = None
    last_fetched: str | None = None
    results: list[SearchResult] = []

    # Stage 1: basic scraping (HTTP + BeautifulSoup)
    try:
        html, _ = fetch_html_http(
            search_url,
            timeout=SETTINGS.search_timeout_s,
            extra_patterns=patterns,
            settle_after_load=True,
        )
        last_fetched = html
        results = _parse_serp(adapter, html, search_url)
        if results:
            logger.info("[%s] SERP stage 1 basic (%d results)", adapter.display_name, len(results))
            return results, html
        cached_html = html
    except ExtractionFailure as e:
        logger.info("[%s] SERP stage 1 failed: %s", adapter.display_name, e)

    # Stage 2: browser-based scraping (Playwright + BeautifulSoup)
    try:
        html = fetch_html_playwright(search_url, strict_bot_check=True)
        last_fetched = html
        if is_bot_page(html, patterns):
            raise ExtractionFailure("bot on search", None)
        results = _parse_serp(adapter, html, search_url)
        if results:
            logger.info("[%s] SERP stage 2 browser (%d results)", adapter.display_name, len(results))
            return results, html
        cached_html = html
    except ExtractionFailure as e:
        logger.info("[%s] SERP stage 2 failed: %s", adapter.display_name, e)

    # Stage 3: LLM-based extraction on HTML from earlier stages
    html_for_llm = cached_html
    if not html_for_llm:
        try:
            html_for_llm = fetch_html_playwright(search_url, strict_bot_check=False)
            last_fetched = html_for_llm or last_fetched
        except ExtractionFailure as e:
            logger.info("[%s] SERP stage 3 prefetch failed: %s", adapter.display_name, e)

    if html_for_llm:
        try:
            results = parse_serp_with_llm(html_for_llm, search_url, adapter)
            if results:
                logger.info("[%s] SERP stage 3 LLM (%d results)", adapter.display_name, len(results))
                return results, html_for_llm
        except ExtractionFailure as e:
            logger.info("[%s] SERP stage 3 failed: %s", adapter.display_name, e)

    # Stage 4: Firecrawl API (fetch HTML + parse, then structured extract)
    try:
        html = fetch_html_firecrawl(search_url)
        last_fetched = html
        results = _parse_serp(adapter, html, search_url)
        if results:
            logger.info(
                "[%s] SERP stage 4 Firecrawl+parse (%d results)",
                adapter.display_name,
                len(results),
            )
            return results, html
    except ExtractionFailure as e:
        logger.info("[%s] SERP stage 4 fetch failed: %s", adapter.display_name, e)

    if query:
        try:
            results = firecrawl_extract_serp(adapter, search_url, query)
            if results:
                logger.info(
                    "[%s] SERP stage 4 Firecrawl extract (%d results)",
                    adapter.display_name,
                    len(results),
                )
                return results, last_fetched
        except Exception as e:
            logger.info("[%s] SERP stage 4 extract failed: %s", adapter.display_name, e)

    return [], last_fetched
