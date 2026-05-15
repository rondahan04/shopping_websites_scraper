"""Run search → match → extract for a single site."""

from __future__ import annotations

import logging

from extraction.pipeline import run_extraction_pipeline
from extraction.search_fetch import fetch_search_results
from matching.scorer import pick_best_match
from models import ProductRow
from sites.base import SiteAdapter

logger = logging.getLogger(__name__)


def scrape_site(adapter: SiteAdapter, query: str) -> ProductRow:
    try:
        search_url = adapter.build_search_url(query)
        logger.info("[%s] Searching: %s", adapter.display_name, search_url)
        results = fetch_search_results(adapter, search_url)

        if not results:
            logger.warning("[%s] No search results parsed", adapter.display_name)
            return ProductRow.failed(adapter.display_name)

        match, candidates = pick_best_match(query, results)
        if not match:
            logger.warning("[%s] No match selected", adapter.display_name)
            return ProductRow.failed(adapter.display_name)

        logger.info(
            "[%s] Matched (score=%.1f): %s",
            adapter.display_name,
            candidates[0].score if candidates else 0,
            match.title[:80],
        )
        return run_extraction_pipeline(adapter, match.url)
    except Exception as e:
        logger.exception("[%s] Unexpected error: %s", adapter.display_name, e)
        return ProductRow.failed(adapter.display_name)
