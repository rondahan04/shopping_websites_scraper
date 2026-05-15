"""Run search → match → extract for a single site."""

from __future__ import annotations

import logging
from dataclasses import replace

from extraction.pipeline import run_extraction_pipeline
from extraction.search_fetch import fetch_search_results
from matching.scorer import pick_best_match
from models import ProductRow
from sites.base import SiteAdapter
from utils.html_debug import get_html_debug_dir, write_site_html

logger = logging.getLogger(__name__)


def scrape_site(adapter: SiteAdapter, query: str) -> ProductRow:
    capture = get_html_debug_dir() is not None
    serp_path: str | None = None
    prod_path: str | None = None

    try:
        search_url = adapter.build_search_url(query)
        logger.info("[%s] Searching: %s", adapter.display_name, search_url)
        results, serp_html = fetch_search_results(adapter, search_url)

        if capture and serp_html:
            try:
                serp_path = write_site_html(adapter.display_name, "serp", serp_html)
            except OSError as e:
                logger.warning("[%s] could not write SERP html: %s", adapter.display_name, e)

        if not results:
            logger.warning("[%s] No search results parsed", adapter.display_name)
            row = ProductRow.failed(adapter.display_name)
            if serp_path:
                row = replace(row, serp_html_path=serp_path)
            return row

        match, candidates = pick_best_match(query, results)
        if not match:
            logger.warning("[%s] No match selected", adapter.display_name)
            row = ProductRow.failed(adapter.display_name)
            if serp_path:
                row = replace(row, serp_html_path=serp_path)
            return row

        logger.info(
            "[%s] Matched (score=%.1f): %s",
            adapter.display_name,
            candidates[0].score if candidates else 0,
            match.title[:80],
        )
        row, prod_html = run_extraction_pipeline(
            adapter,
            match.url,
            capture_product_html=capture,
        )
        if capture and prod_html:
            try:
                prod_path = write_site_html(adapter.display_name, "product", prod_html)
            except OSError as e:
                logger.warning("[%s] could not write product html: %s", adapter.display_name, e)

        if serp_path or prod_path:
            row = replace(
                row,
                serp_html_path=serp_path or row.serp_html_path,
                product_html_path=prod_path or row.product_html_path,
            )
        return row
    except Exception as e:
        logger.exception("[%s] Unexpected error: %s", adapter.display_name, e)
        return ProductRow.failed(adapter.display_name)
