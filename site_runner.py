"""Run search → match → extract for a single site."""

from __future__ import annotations

import logging
from dataclasses import replace
from urllib.parse import urlparse

from config import SETTINGS
from extraction.llm_extract import parse_serp_with_llm
from extraction.llm_price_verify import llm_verify_scraped_price
from extraction.pipeline import run_extraction_pipeline, run_extraction_pipeline_price_retry
from extraction.search_fetch import fetch_search_results
from extraction.llm_site_search_plan import SiteSearchPlan
from extraction.llm_title_verify import TitleVerifyResult, llm_verify_listing_title
from extraction.search_attempts import search_attempt_queries
from extraction.serp_fallback import (
    firecrawl_extract_serp,
    google_site_search_discover,
    pdp_fallback_candidates,
)
from matching.condition import listing_is_non_new, query_requests_used_condition
from matching.normalize import (
    DEVICE_QUERY_MARKERS,
    has_accessory_conflict,
    has_chip_generation_mismatch,
    has_earbuds_vs_headphones_conflict,
    is_amazon_earbuds_asin_for_headphone_query,
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
from utils.parsing import parse_price

logger = logging.getLogger(__name__)


def _should_skip_serp_candidate(query: str, listing: SearchResult) -> bool:
    """Skip renewed/refurb/open-box SERP rows when the user wants new retail."""
    if query_requests_used_condition(query):
        return False
    return listing_is_non_new(listing.title)


def _row_passes_price_verify(
    adapter: SiteAdapter,
    *,
    user_query: str,
    serp_title: str,
    row: ProductRow,
) -> bool:
    if row.status != "Success" or not row_has_scraped_price(row):
        return False
    title = row.product_title if row.product_title and row.product_title != "N/A" else serp_title
    if not query_requests_used_condition(user_query) and listing_is_non_new(title):
        logger.info(
            "[%s] Rejecting non-new PDP title for new-retail query: %s",
            adapter.display_name,
            title[:72],
        )
        return False
    found = parse_price(row.price)
    if found is None:
        return False
    verify = llm_verify_scraped_price(
        user_query=user_query,
        product_title=title,
        scraped_price=found,
        retailer=adapter.display_name,
        source_url=row.source_url,
    )
    if verify.plausible:
        expected = (
            f", expected ~${verify.expected_price_usd:,.2f}"
            if verify.expected_price_usd
            else ""
        )
        logger.info(
            "[%s] LLM price verify OK ($%s%s): %s",
            adapter.display_name,
            f"{found:,.2f}",
            expected,
            verify.reason,
        )
        return True
    expected_note = (
        f" (LLM expected ~${verify.expected_price_usd:,.2f})"
        if verify.expected_price_usd
        else ""
    )
    logger.warning(
        "[%s] LLM price verify rejected scraped $%s%s: %s",
        adapter.display_name,
        f"{found:,.2f}",
        expected_note,
        verify.reason,
    )
    return False


def _finalize_verified_row(
    row: ProductRow,
    *,
    serp_path: str | None,
    prod_path: str | None,
) -> ProductRow:
    if serp_path or prod_path:
        return replace(
            row,
            serp_html_path=serp_path or row.serp_html_path,
            product_html_path=prod_path or row.product_html_path,
        )
    return row


def _failed_after_price_verify(
    adapter: SiteAdapter,
    *,
    serp_path: str | None,
    prod_path: str | None,
) -> ProductRow:
    logger.warning(
        "[%s] Marking Failed after LLM price verify (no plausible price from SERP candidates)",
        adapter.display_name,
    )
    failed = ProductRow.failed(adapter.display_name)
    return _finalize_verified_row(failed, serp_path=serp_path, prod_path=prod_path)


def _try_alternate_serp_candidates(
    adapter: SiteAdapter,
    *,
    user_query: str,
    candidates: list[MatchCandidate],
    skip_urls: set[str],
    capture: bool,
    serp_path: str | None,
    max_alternates: int = 5,
) -> ProductRow | None:
    """After a bad PDP on one SERP row, try other ranked candidates (new URL each time)."""
    tried = 0
    for cand in sorted(candidates, key=lambda c: c.score, reverse=True):
        alt = cand.result
        if alt.url in skip_urls:
            continue
        if _should_skip_serp_candidate(user_query, alt):
            logger.info(
                "[%s] Skipping alternate (non-new SERP title): %s",
                adapter.display_name,
                alt.title[:72],
            )
            skip_urls.add(alt.url)
            continue
        if _listing_model_mismatch(user_query, alt.title, alt.url):
            continue
        if not pdp_url_reachable(alt.url):
            continue
        tried += 1
        if tried > max_alternates:
            break
        logger.info(
            "[%s] Trying alternate SERP candidate (score=%.1f): %s",
            adapter.display_name,
            cand.score,
            alt.title[:72],
        )
        alt_row, alt_html = run_extraction_pipeline(
            adapter, alt.url, capture_product_html=capture
        )
        alt_prod_path: str | None = None
        if capture and alt_html:
            try:
                alt_prod_path = write_site_html(adapter.display_name, "product", alt_html)
            except OSError as e:
                logger.warning(
                    "[%s] could not write product html for alternate: %s",
                    adapter.display_name,
                    e,
                )
        skip_urls.add(alt.url)
        if _row_passes_price_verify(
            adapter, user_query=user_query, serp_title=alt.title, row=alt_row
        ):
            return _finalize_verified_row(
                alt_row, serp_path=serp_path, prod_path=alt_prod_path
            )
    return None


def _apply_llm_price_verify(
    adapter: SiteAdapter,
    *,
    user_query: str,
    match: SearchResult,
    row: ProductRow,
    candidates: list[MatchCandidate],
    capture: bool,
    serp_path: str | None,
    prod_path: str | None,
) -> ProductRow:
    """Reject implausible prices; retry same URL with heavier methods, then other SERP rows."""
    if row.status != "Success" or not row_has_scraped_price(row):
        return row

    if _row_passes_price_verify(
        adapter, user_query=user_query, serp_title=match.title, row=row
    ):
        return row

    skip_urls: set[str] = {match.url}
    retry_row, retry_html = run_extraction_pipeline_price_retry(
        adapter, match.url, capture_product_html=capture
    )
    retry_prod_path = prod_path
    if capture and retry_html:
        try:
            retry_prod_path = write_site_html(adapter.display_name, "product", retry_html)
        except OSError as e:
            logger.warning(
                "[%s] could not write product html on price retry: %s",
                adapter.display_name,
                e,
            )
    if _row_passes_price_verify(
        adapter, user_query=user_query, serp_title=match.title, row=retry_row
    ):
        return _finalize_verified_row(
            retry_row, serp_path=serp_path, prod_path=retry_prod_path
        )

    if candidates:
        alt_row = _try_alternate_serp_candidates(
            adapter,
            user_query=user_query,
            candidates=candidates,
            skip_urls=skip_urls,
            capture=capture,
            serp_path=serp_path,
        )
        if alt_row is not None:
            return alt_row

    return _failed_after_price_verify(
        adapter, serp_path=serp_path, prod_path=retry_prod_path or prod_path
    )


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


def _verify_listing(
    adapter: SiteAdapter, plan: SiteSearchPlan, listing: SearchResult
) -> TitleVerifyResult:
    """GPT gate: scraped SERP title vs plan.match_query; returns match + next action."""
    verdict = llm_verify_listing_title(
        user_query=plan.user_query,
        expected_product_name=plan.match_query,
        scraped_listing_title=listing.title,
        retailer=adapter.display_name,
    )
    if verdict.match:
        logger.info(
            "[%s] LLM title verify OK: %s",
            adapter.display_name,
            verdict.reason[:120],
        )
    else:
        logger.info(
            "[%s] LLM title verify rejected (%s): %s — scraped=%r",
            adapter.display_name,
            verdict.action,
            verdict.reason[:120],
            listing.title[:80],
        )
        if verdict.suggested_search:
            logger.info(
                "[%s] LLM suggests refine search: %r",
                adapter.display_name,
                verdict.suggested_search[:80],
            )
    return verdict


def _llm_accepts_listing(adapter: SiteAdapter, plan: SiteSearchPlan, listing: SearchResult) -> bool:
    return _verify_listing(adapter, plan, listing).match


def _pick_valid_match(
    query: str,
    candidates: list[MatchCandidate],
    adapter: SiteAdapter,
    *,
    plan: SiteSearchPlan | None = None,
) -> tuple[SearchResult | None, list[str]]:
    """Pick best candidate; collect LLM ``refine_search`` queries when titles mismatch."""
    refine_queries: list[str] = []
    for cand in sorted(candidates, key=lambda c: c.score, reverse=True):
        r = cand.result
        if not pdp_url_reachable(r.url):
            logger.info(
                "[%s] Skipping candidate (PDP not reachable): %s",
                adapter.display_name,
                r.url[:100],
            )
            continue
        if _should_skip_serp_candidate(query, r):
            continue
        if _listing_model_mismatch(query, r.title, r.url):
            continue
        if has_accessory_conflict(normalize_text(query), normalize_text(r.title)):
            continue
        if has_earbuds_vs_headphones_conflict(
            normalize_text(query), normalize_text(r.title)
        ):
            continue
        if is_amazon_earbuds_asin_for_headphone_query(normalize_text(query), r.url):
            logger.info(
                "[%s] Skipping candidate (known earbud ASIN for headphone query): %s",
                adapter.display_name,
                r.url[:80],
            )
            continue
        if adapter.domain == "amazon.com" and _amazon_heading_matches_ram_kit_url(r.url, r.title):
            continue
        if plan is not None:
            verdict = _verify_listing(adapter, plan, r)
            if verdict.match:
                return r, refine_queries
            if verdict.action == "refine_search" and verdict.suggested_search:
                if verdict.suggested_search not in refine_queries:
                    refine_queries.append(verdict.suggested_search)
            continue
        return r, refine_queries
    return None, refine_queries


def _try_refined_serp_matches(
    adapter: SiteAdapter,
    plan: SiteSearchPlan,
    refine_queries: list[str],
    *,
    max_attempts: int = 2,
) -> SearchResult | None:
    """Run extra SERP fetches using LLM-suggested search strings after title rejections."""
    seen: set[str] = set()
    for rq in refine_queries:
        key = rq.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        if len(seen) > max_attempts:
            break
        search_url = adapter.build_search_url(rq)
        logger.info("[%s] Acting on LLM refine_search: %s", adapter.display_name, search_url)
        results, _ = fetch_search_results(adapter, search_url, query=rq)
        results = _drop_accessory_serp_rows(plan.match_query, results)
        if not results:
            continue
        _, candidates = pick_best_match(plan.match_query, results)
        if not candidates:
            continue
        match, _ = _pick_valid_match(plan.match_query, candidates, adapter, plan=plan)
        if match and not _listing_model_mismatch(plan.match_query, match.title, match.url):
            if not _listing_looks_like_accessory_for_query(plan.match_query, match.title):
                return match
    return None


def _accept_discovered_match(
    adapter: SiteAdapter,
    candidate: SearchResult | None,
    query: str,
    *,
    plan: SiteSearchPlan | None = None,
) -> SearchResult | None:
    """Reject hallucinated Google/Firecrawl PDP URLs (404, search echo titles)."""
    if candidate is None:
        return None
    if not pdp_url_reachable(candidate.url):
        return None
    qn = normalize_text(query).normalized
    tn = normalize_text(candidate.title).normalized
    # Reject bare user-query echoes, not legitimate product titles from Google/Firecrawl discover.
    user_qn = normalize_text(plan.user_query if plan else query).normalized
    if tn == user_qn:
        logger.info(
            "[%s] Skipping discovery result (title echoes user query): %s",
            adapter.display_name,
            candidate.title[:72],
        )
        return None
    if _listing_model_mismatch(query, candidate.title, candidate.url):
        return None
    if has_accessory_conflict(normalize_text(query), normalize_text(candidate.title)):
        return None
    if plan is not None and not _llm_accepts_listing(adapter, plan, candidate):
        return None
    return candidate


def _try_firecrawl_extract_match(
    adapter: SiteAdapter,
    search_url: str,
    query: str,
    *,
    plan: SiteSearchPlan | None = None,
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
        match, _ = _pick_valid_match(query, candidates, adapter, plan=plan)
    elif match and not pdp_url_reachable(match.url):
        match = None
    return match, candidates


def _extend_refine_queries(dest: list[str], src: list[str]) -> None:
    for q in src:
        if q and q not in dest:
            dest.append(q)


def _amazon_pick_safe_match(
    candidates: list[MatchCandidate],
    adapter: SiteAdapter,
    *,
    plan: SiteSearchPlan | None = None,
) -> tuple[SearchResult | None, list[str]]:
    refine_queries: list[str] = []
    for cand in candidates:
        r = cand.result
        if _should_skip_serp_candidate(plan.match_query if plan else "", r):
            continue
        if _amazon_heading_matches_ram_kit_url(r.url, r.title):
            logger.info(
                "[Amazon.com] Skipping SERP pick (RAM module URL vs laptop-like heading): %s",
                r.title[:72],
            )
            continue
        if plan is not None:
            verdict = _verify_listing(adapter, plan, r)
            if verdict.match:
                return r, refine_queries
            if verdict.action == "refine_search" and verdict.suggested_search:
                _extend_refine_queries(refine_queries, [verdict.suggested_search])
            continue
        return r, refine_queries
    return None, refine_queries


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
                    adapter,
                    google_site_search_discover(adapter, query),
                    query,
                    plan=plan,
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

        refine_queries: list[str] = []
        match, candidates = pick_best_match(query, results)
        if candidates:
            match, rq = _pick_valid_match(query, candidates, adapter, plan=plan)
            _extend_refine_queries(refine_queries, rq)
        if match and (
            _listing_model_mismatch(query, match.title, match.url)
            or _listing_looks_like_accessory_for_query(query, match.title)
        ):
            match = None
        if adapter.domain == "amazon.com" and candidates and match is None:
            match, rq = _amazon_pick_safe_match(candidates, adapter, plan=plan)
            _extend_refine_queries(refine_queries, rq)
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
                        match, rq = _pick_valid_match(query, candidates, adapter, plan=plan)
                        _extend_refine_queries(refine_queries, rq)
                    if match and (
                        _listing_model_mismatch(query, match.title, match.url)
                        or _listing_looks_like_accessory_for_query(query, match.title)
                    ):
                        match = None
                    if adapter.domain == "amazon.com" and candidates and match is None:
                        match, rq = _amazon_pick_safe_match(candidates, adapter, plan=plan)
                        _extend_refine_queries(refine_queries, rq)
        if not match:
            match, candidates = _try_firecrawl_extract_match(
                adapter, search_url, query, plan=plan
            )

        if not match and refine_queries:
            refined = _try_refined_serp_matches(adapter, plan, refine_queries)
            if refined:
                match = refined
                candidates = [MatchCandidate(refined, 100.0, {})]

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
                match, rq = _pick_valid_match(
                    query, [MatchCandidate(r, 100.0, {}) for r in fb], adapter, plan=plan
                )
                _extend_refine_queries(refine_queries, rq)
                if (
                    not match
                    and fb
                    and pdp_url_reachable(fb[0].url)
                    and (plan is None or _llm_accepts_listing(adapter, plan, fb[0]))
                ):
                    match = fb[0]
                candidates = [MatchCandidate(r, 100.0, {}) for r in fb]
            if not match:
                discovered = _accept_discovered_match(
                    adapter,
                    google_site_search_discover(adapter, query),
                    query,
                    plan=plan,
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

        verify_candidates = candidates
        if match and not verify_candidates:
            verify_candidates = [MatchCandidate(match, log_score, {})]

        row = _apply_llm_price_verify(
            adapter,
            user_query=query,
            match=match,
            candidates=verify_candidates,
            row=row,
            capture=capture,
            serp_path=serp_path,
            prod_path=prod_path,
        )

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
