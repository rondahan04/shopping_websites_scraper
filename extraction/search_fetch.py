"""Search-page fetch with M1→M4 style fallback before parsing SERP."""

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
    """Fetch search HTML and parse results using HTTP → Playwright → LLM → Firecrawl.

    Returns ``(results, serp_html)`` where ``serp_html`` is the document that produced
    ``results`` when non-empty; otherwise the last HTML fetched for forensics (may be a
    bot or empty-parse page), or ``None``.
    """
    patterns = adapter.bot_check_patterns()
    cached_html: str | None = None
    last_fetched: str | None = None
    results: list[SearchResult] = []

    # M1: HTTP (httpx) + BeautifulSoup
    try:
        html, _ = fetch_html_http(
            search_url,
            timeout=SETTINGS.search_timeout_s,
            extra_patterns=patterns,
        )
        last_fetched = html
        results = _parse_serp(adapter, html, search_url)
        if results:
            logger.info("[%s] SERP via http (%d results)", adapter.display_name, len(results))
            return results, html
        cached_html = html
    except ExtractionFailure as e:
        logger.info("[%s] search M1 failed: %s", adapter.display_name, e)

    # Best Buy SERP is often a JS shell over Scrapling; try Playwright before LLM on empty DOM.
    if not results and adapter.domain == "bestbuy.com":
        try:
            html = fetch_html_playwright(search_url, strict_bot_check=False)
            last_fetched = html
            results = _parse_serp(adapter, html, search_url)
            if results:
                logger.info(
                    "[%s] SERP via playwright (bestbuy early) (%d results)",
                    adapter.display_name,
                    len(results),
                )
                return results, html
            cached_html = html
        except ExtractionFailure as e:
            logger.info("[%s] bestbuy early playwright failed: %s", adapter.display_name, e)

    # M2: Playwright
    try:
        html = fetch_html_playwright(search_url, strict_bot_check=True)
        last_fetched = html
        if is_bot_page(html, patterns):
            raise ExtractionFailure("bot on search", None)
        results = _parse_serp(adapter, html, search_url)
        if results:
            logger.info("[%s] SERP via playwright (%d results)", adapter.display_name, len(results))
            return results, html
        cached_html = html
    except ExtractionFailure as e:
        logger.info("[%s] search M2 failed: %s", adapter.display_name, e)

    # M3: LLM SERP parse
    html_for_llm = cached_html
    if not html_for_llm:
        try:
            html_for_llm = fetch_html_playwright(search_url, strict_bot_check=False)
            last_fetched = html_for_llm or last_fetched
        except ExtractionFailure as e:
            logger.info("[%s] search M3 prefetch failed: %s", adapter.display_name, e)

    if html_for_llm:
        try:
            results = parse_serp_with_llm(html_for_llm, search_url, adapter)
            logger.info("[%s] SERP via llm (%d results)", adapter.display_name, len(results))
            return results, html_for_llm
        except ExtractionFailure as e:
            logger.info("[%s] search M3 failed: %s", adapter.display_name, e)

    # M4: Firecrawl HTML → parse / LLM
    try:
        html = fetch_html_firecrawl(search_url)
        last_fetched = html
        results = _parse_serp(adapter, html, search_url)
        if results:
            logger.info("[%s] SERP via firecrawl+parse (%d results)", adapter.display_name, len(results))
            return results, html
        results = parse_serp_with_llm(html, search_url, adapter)
        logger.info("[%s] SERP via firecrawl+llm (%d results)", adapter.display_name, len(results))
        return results, html
    except ExtractionFailure as e:
        logger.info("[%s] search M4 failed: %s", adapter.display_name, e)

    # M5: Firecrawl structured SERP extract (works when HTML has no parseable grid).
    if query:
        try:
            results = firecrawl_extract_serp(adapter, search_url, query)
            if results:
                logger.info(
                    "[%s] SERP via firecrawl extract (%d results)",
                    adapter.display_name,
                    len(results),
                )
                return results, last_fetched
        except Exception as e:
            logger.info("[%s] search M5 failed: %s", adapter.display_name, e)

    return [], last_fetched
