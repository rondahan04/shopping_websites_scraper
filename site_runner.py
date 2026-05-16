"""Run search → match → extract for a single site."""

from __future__ import annotations

import logging
from dataclasses import replace
from urllib.parse import urlparse

from config import SETTINGS
from extraction.llm_extract import parse_serp_with_llm
from extraction.pipeline import run_extraction_pipeline
from extraction.search_fetch import fetch_search_results
from extraction.llm_site_search_plan import SiteSearchPlan
from extraction.search_attempts import search_attempt_queries
from extraction.serp_fallback import (
    firecrawl_extract_serp,
    google_site_search_discover,
    pdp_fallback_candidates,
)
from matching.normalize import (
    DEVICE_QUERY_MARKERS,
    has_accessory_conflict,
    has_chip_generation_mismatch,
    has_model_code_mismatch,
    normalize_text,
)
from matching.scorer import pick_best_match
from models import (
    ExtractionFailure,
    ExtractionMethod,
    MatchCandidate,
    ProductFields,
    ProductRow,
    SearchResult,
    row_has_scraped_price,
)
from sites.amazon import amazon_heading_conflicts_with_ram_module_slug
from sites.base import SiteAdapter
from utils.amazon_resolve import amazon_resolved_product_path
from utils.html_debug import get_html_debug_dir, write_site_html
from utils.pdp_url import pdp_url_reachable

logger = logging.getLogger(__name__)


def _amazon_heading_matches_ram_kit_url(candidate_url: str, title: str) -> bool:
    seed_path = urlparse(candidate_url).path
    if amazon_heading_conflicts_with_ram_module_slug(seed_path, title):
        return True
    canon_path = amazon_resolved_product_path(candidate_url)
    return bool(canon_path and amazon_heading_conflicts_with_ram_module_slug(canon_path, title))


def _drop_accessory_serp_rows(query: str, results: list[SearchResult]) -> list[SearchResult]:
    qn = normalize_text(query)
    kept = [
        r
        for r in results
        if not has_accessory_conflict(qn, normalize_text(r.title))
    ]
    if kept:
        return kept
    if any(m in qn.normalized for m in DEVICE_QUERY_MARKERS):
        return []
    return results


def _listing_looks_like_accessory_for_query(query: str, product_title: str) -> bool:
    return has_accessory_conflict(normalize_text(query), normalize_text(product_title))


def _is_known_fallback_pdp(adapter: SiteAdapter, query: str, url: str) -> bool:
    canon = url.split("?")[0].lower()
    return any(f.url.split("?")[0].lower() == canon for f in pdp_fallback_candidates(adapter, query))


def _listing_model_mismatch(query: str, title: str, url: str = "") -> bool:
    """PDP title must carry query model codes (URL path alone is not enough)."""
    qn = normalize_text(query)
    tn = normalize_text(title)
    return has_model_code_mismatch(qn, tn) or has_chip_generation_mismatch(qn, tn)


def _pick_valid_match(
    query: str,
    candidates: list[MatchCandidate],
    adapter: SiteAdapter,
) -> SearchResult | None:
    for cand in sorted(candidates, key=lambda c: c.score, reverse=True):
        r = cand.result
        if not pdp_url_reachable(r.url):
            logger.info(
                "[%s] Skipping candidate (PDP not reachable): %s",
                adapter.display_name,
                r.url[:100],
            )
            continue
        if _listing_model_mismatch(query, r.title, r.url):
            continue
        if has_accessory_conflict(normalize_text(query), normalize_text(r.title)):
            continue
        if adapter.domain == "amazon.com" and _amazon_heading_matches_ram_kit_url(r.url, r.title):
            continue
        return r
    return None


def _accept_discovered_match(
    adapter: SiteAdapter,
    candidate: SearchResult | None,
    query: str,
) -> SearchResult | None:
    """Reject hallucinated Google/Firecrawl PDP URLs (404, search echo titles)."""
    if candidate is None:
        return None
    if not pdp_url_reachable(candidate.url):
        return None
    qn = normalize_text(query).normalized
    tn = normalize_text(candidate.title).normalized
    if tn == qn or (len(tn) > 40 and tn in qn):
        logger.info(
            "[%s] Skipping discovery result (title echoes query): %s",
            adapter.display_name,
            candidate.title[:72],
        )
        return None
    if _listing_model_mismatch(query, candidate.title, candidate.url):
        return None
    if has_accessory_conflict(normalize_text(query), normalize_text(candidate.title)):
        return None
    return candidate


def _try_firecrawl_extract_match(
    adapter: SiteAdapter,
    search_url: str,
    query: str,
) -> tuple[SearchResult | None, list[MatchCandidate]]:
    extracted = firecrawl_extract_serp(adapter, search_url, query)
    if not extracted:
        return None, []
    extracted = _drop_accessory_serp_rows(query, extracted)
    if not extracted:
        return None, []
    logger.info(
        "[%s] SERP via firecrawl extract (match retry) (%d results)",
        adapter.display_name,
        len(extracted),
    )
    match, candidates = pick_best_match(query, extracted)
    if candidates:
        match = _pick_valid_match(query, candidates, adapter)
    elif match and not pdp_url_reachable(match.url):
        match = None
    return match, candidates


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


def scrape_site(adapter: SiteAdapter, plan: SiteSearchPlan) -> ProductRow:
    """Search and extract one retailer using LLM-tuned search strings and match_query."""
    query = plan.match_query
    capture = get_html_debug_dir() is not None
    serp_path: str | None = None
    prod_path: str | None = None

    try:
        results: list[SearchResult] = []
        serp_html: str | None = None
        for attempt_q in search_attempt_queries(plan):
            search_url = adapter.build_search_url(attempt_q)
            logger.info("[%s] Searching: %s", adapter.display_name, search_url)
            results, serp_html = fetch_search_results(adapter, search_url, query=attempt_q)
            if results:
                break

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
            results = pdp_fallback_candidates(adapter, query)
            if results:
                logger.info(
                    "[%s] Using PDP fallback candidate (%d)",
                    adapter.display_name,
                    len(results),
                )
            else:
                discovered = _accept_discovered_match(
                    adapter, google_site_search_discover(adapter, query), query
                )
                if discovered:
                    results = [discovered]
                    logger.info("[%s] Using google site-search PDP discovery", adapter.display_name)

        if not results:
            logger.warning("[%s] No search results parsed", adapter.display_name)
            row = ProductRow.failed(adapter.display_name)
            if serp_path:
                row = replace(row, serp_html_path=serp_path)
            return row

        results = _drop_accessory_serp_rows(query, results)

        match, candidates = pick_best_match(query, results)
        if candidates:
            match = _pick_valid_match(query, candidates, adapter)
        if match and (
            _listing_model_mismatch(query, match.title, match.url)
            or _listing_looks_like_accessory_for_query(query, match.title)
        ):
            match = None
        if adapter.domain == "amazon.com" and candidates and match is None:
            match = _amazon_pick_safe_match(candidates)
        if not match and serp_html and SETTINGS.openai_api_key:
            try:
                alt = parse_serp_with_llm(serp_html, search_url, adapter)
            except ExtractionFailure as e:
                logger.info("[%s] SERP llm reparse after no match skipped: %s", adapter.display_name, e)
            else:
                if alt:
                    alt = _drop_accessory_serp_rows(query, alt)
                    logger.info(
                        "[%s] SERP via llm after no match (%d results)",
                        adapter.display_name,
                        len(alt),
                    )
                    match, candidates = pick_best_match(query, alt)
                    if candidates:
                        match = _pick_valid_match(query, candidates, adapter)
                    if match and (
                        _listing_model_mismatch(query, match.title, match.url)
                        or _listing_looks_like_accessory_for_query(query, match.title)
                    ):
                        match = None
                    if adapter.domain == "amazon.com" and candidates and match is None:
                        match = _amazon_pick_safe_match(candidates)
        if not match:
            match, candidates = _try_firecrawl_extract_match(adapter, search_url, query)

        if match and not pdp_url_reachable(match.url):
            logger.info(
                "[%s] Discarding match: PDP URL not reachable (%s)",
                adapter.display_name,
                match.url[:100],
            )
            match = None

        if not match:
            fb = pdp_fallback_candidates(adapter, query)
            if fb:
                logger.info(
                    "[%s] Retrying match with PDP fallback (%d)",
                    adapter.display_name,
                    len(fb),
                )
                match = _pick_valid_match(query, [MatchCandidate(r, 100.0, {}) for r in fb], adapter)
                if not match and fb and pdp_url_reachable(fb[0].url):
                    match = fb[0]
                candidates = [MatchCandidate(r, 100.0, {}) for r in fb]
            if not match:
                discovered = _accept_discovered_match(
                    adapter, google_site_search_discover(adapter, query), query
                )
                if discovered:
                    match = discovered
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
        if row.status == "Success" and _listing_looks_like_accessory_for_query(
            query, row.product_title
        ):
            logger.warning(
                "[%s] Rejecting accessory PDP for device query: %s",
                adapter.display_name,
                row.product_title[:72],
            )
            row = ProductRow.failed(adapter.display_name)
            if serp_path:
                row = replace(row, serp_html_path=serp_path)
        elif row.status == "Success" and _listing_model_mismatch(
            query, row.product_title, match.url
        ):
            logger.warning(
                "[%s] Rejecting PDP with wrong model code vs query: %s",
                adapter.display_name,
                row.product_title[:72],
            )
            row = ProductRow.failed(adapter.display_name)
            if serp_path:
                row = replace(row, serp_html_path=serp_path)

        if not row_has_scraped_price(row) and match and _is_known_fallback_pdp(
            adapter, query, match.url
        ):
            logger.warning(
                "[%s] Known PDP fallback matched but price not extracted — marking Failed",
                adapter.display_name,
            )
            row = replace(
                row,
                website=adapter.display_name,
                product_title=match.title,
                source_url=match.url,
                status="Failed",
                price="N/A",
                average_rating="N/A",
                review_count="N/A",
            )
            if serp_path or prod_path:
                row = replace(
                    row,
                    serp_html_path=serp_path or row.serp_html_path,
                    product_html_path=prod_path or row.product_html_path,
                )
        elif not row_has_scraped_price(row) and row.status == "Success":
            logger.warning(
                "[%s] No price on PDP — marking Failed (Success requires scraped price)",
                adapter.display_name,
            )
            row = replace(row, status="Failed")
        return row
    except Exception as e:
        logger.exception("[%s] Unexpected error: %s", adapter.display_name, e)
        return ProductRow.failed(adapter.display_name)
