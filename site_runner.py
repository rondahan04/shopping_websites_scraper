"""Run search → match → extract for a single site."""

from __future__ import annotations

import logging
from dataclasses import replace
from urllib.parse import urlparse

from config import SETTINGS
from extraction.llm_extract import parse_serp_with_llm
from extraction.pipeline import run_extraction_pipeline
from extraction.search_fetch import fetch_search_results
from matching.scorer import pick_best_match
from models import ExtractionFailure, MatchCandidate, ProductRow, SearchResult
from sites.amazon import amazon_heading_conflicts_with_ram_module_slug
from sites.base import SiteAdapter
from utils.amazon_resolve import amazon_resolved_product_path
from utils.html_debug import get_html_debug_dir, write_site_html

logger = logging.getLogger(__name__)


def _amazon_heading_matches_ram_kit_url(candidate_url: str, title: str) -> bool:
    seed_path = urlparse(candidate_url).path
    if amazon_heading_conflicts_with_ram_module_slug(seed_path, title):
        return True
    canon_path = amazon_resolved_product_path(candidate_url)
    return bool(canon_path and amazon_heading_conflicts_with_ram_module_slug(canon_path, title))


def _amazon_pick_safe_match(candidates: list[MatchCandidate]) -> SearchResult | None:
    for cand in candidates:
        r = cand.result
        if _amazon_heading_matches_ram_kit_url(r.url, r.title):
            logger.info(
                "[Amazon.com] Skipping SERP pick (RAM module URL vs laptop-like heading): %s",
                r.title[:72],
            )
            continue
        return r
    return None


def scrape_site(adapter: SiteAdapter, query: str) -> ProductRow:
    capture = get_html_debug_dir() is not None
    serp_path: str | None = None
    prod_path: str | None = None

    try:
        search_url = adapter.build_search_url(query)
        logger.info("[%s] Searching: %s", adapter.display_name, search_url)
        results, serp_html = fetch_search_results(adapter, search_url)

        if not results and serp_html and SETTINGS.openai_api_key:
            try:
                results = parse_serp_with_llm(serp_html, search_url, adapter)
                logger.info(
                    "[%s] SERP via llm (no structured rows; %d results)",
                    adapter.display_name,
                    len(results),
                )
            except ExtractionFailure as e:
                logger.info("[%s] SERP llm empty-parse remedy skipped: %s", adapter.display_name, e)

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
        if adapter.domain == "amazon.com" and candidates:
            safe_amazon = _amazon_pick_safe_match(candidates)
            match = safe_amazon
        if not match and serp_html and SETTINGS.openai_api_key:
            try:
                alt = parse_serp_with_llm(serp_html, search_url, adapter)
            except ExtractionFailure as e:
                logger.info("[%s] SERP llm reparse after no match skipped: %s", adapter.display_name, e)
            else:
                if alt:
                    logger.info(
                        "[%s] SERP via llm after no match (%d results)",
                        adapter.display_name,
                        len(alt),
                    )
                    match, candidates = pick_best_match(query, alt)
                    if adapter.domain == "amazon.com" and candidates:
                        match = _amazon_pick_safe_match(candidates)
        if not match:
            logger.warning("[%s] No match selected", adapter.display_name)
            row = ProductRow.failed(adapter.display_name)
            if serp_path:
                row = replace(row, serp_html_path=serp_path)
            return row

        log_score = next(
            (c.score for c in candidates if c.result.url == match.url),
            0.0,
        )
        logger.info(
            "[%s] Matched (score=%.1f): %s",
            adapter.display_name,
            log_score,
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
