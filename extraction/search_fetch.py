"""Search-page fetch with M1→M4 style fallback before parsing SERP."""

from __future__ import annotations

import logging

from config import SETTINGS
from extraction.firecrawl_extract import fetch_html_firecrawl
from extraction.llm_extract import parse_serp_with_llm
from extraction.playwright_extract import fetch_html_playwright
from models import ExtractionFailure, SearchResult
from sites.base import SiteAdapter
from utils.http_client import fetch_url
from validation.fields import is_bot_page

logger = logging.getLogger(__name__)


def _parse_serp(adapter: SiteAdapter, html: str, search_url: str) -> list[SearchResult]:
    if is_bot_page(html, adapter.bot_check_patterns()):
        return []
    return adapter.parse_search_results(html, search_url)


def fetch_search_results(adapter: SiteAdapter, search_url: str) -> list[SearchResult]:
    """Fetch search HTML and parse results using requests → Playwright → LLM → Firecrawl."""
    patterns = adapter.bot_check_patterns()
    cached_html: str | None = None

    # M1: requests
    try:
        html, _ = fetch_url(
            search_url,
            timeout=SETTINGS.search_timeout_s,
            extra_patterns=patterns,
        )
        results = _parse_serp(adapter, html, search_url)
        if results:
            logger.info("[%s] SERP via requests (%d results)", adapter.display_name, len(results))
            return results
        cached_html = html
    except ExtractionFailure as e:
        logger.info("[%s] search M1 failed: %s", adapter.display_name, e)

    # M2: Playwright
    try:
        html = fetch_html_playwright(search_url, strict_bot_check=True)
        if is_bot_page(html, patterns):
            raise ExtractionFailure("bot on search", None)
        results = adapter.parse_search_results(html, search_url)
        if results:
            logger.info("[%s] SERP via playwright (%d results)", adapter.display_name, len(results))
            return results
        cached_html = html
    except ExtractionFailure as e:
        logger.info("[%s] search M2 failed: %s", adapter.display_name, e)

    # M3: LLM SERP parse
    html_for_llm = cached_html
    if not html_for_llm:
        try:
            html_for_llm = fetch_html_playwright(search_url, strict_bot_check=False)
        except ExtractionFailure as e:
            logger.info("[%s] search M3 prefetch failed: %s", adapter.display_name, e)

    if html_for_llm:
        try:
            results = parse_serp_with_llm(html_for_llm, search_url, adapter)
            logger.info("[%s] SERP via llm (%d results)", adapter.display_name, len(results))
            return results
        except ExtractionFailure as e:
            logger.info("[%s] search M3 failed: %s", adapter.display_name, e)

    # M4: Firecrawl HTML → parse / LLM
    try:
        html = fetch_html_firecrawl(search_url)
        results = _parse_serp(adapter, html, search_url)
        if results:
            logger.info("[%s] SERP via firecrawl+parse (%d results)", adapter.display_name, len(results))
            return results
        results = parse_serp_with_llm(html, search_url, adapter)
        logger.info("[%s] SERP via firecrawl+llm (%d results)", adapter.display_name, len(results))
        return results
    except ExtractionFailure as e:
        logger.info("[%s] search M4 failed: %s", adapter.display_name, e)

    return []
