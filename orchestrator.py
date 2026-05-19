"""Parallel orchestration across all target sites."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from decimal import Decimal

from config import SETTINGS
from extraction.llm_price_benchmark import llm_reference_prices_for_query, relative_price_gap
from extraction.llm_price_verify import llm_verify_scraped_price
from extraction.llm_site_search_plan import SiteSearchPlan, resolve_site_search_plans

try:
    from api.timeline_log import api_job_id
except ImportError:
    api_job_id = None  # type: ignore[assignment,misc]
from models import ProductRow, row_has_scraped_price
from site_runner import scrape_site
from sites import ALL_ADAPTERS
from sites.base import SiteAdapter
from utils.parsing import parse_price

logger = logging.getLogger(__name__)


def _scrape_and_cleanup(
    adapter: SiteAdapter,
    plan: SiteSearchPlan,
    *,
    timeline_job_id: str | None = None,
) -> ProductRow:
    """Scrape one site and tear down thread-local Playwright resources."""
    from extraction.playwright_extract import shutdown_browser
    from utils.http_fetch import close_http_session

    token = None
    if timeline_job_id and api_job_id is not None:
        token = api_job_id.set(timeline_job_id)

    try:
        return scrape_site(adapter, plan)
    finally:
        if token is not None and api_job_id is not None:
            api_job_id.reset(token)
        try:
            shutdown_browser()
        except Exception:
            pass
        try:
            close_http_session()
        except Exception:
            pass


SiteFinishedFn = Callable[[str, ProductRow], None]
SiteStartedFn = Callable[[str], None]
RecheckBeginFn = Callable[[list[str]], None]


def run_all_sites(
    query: str,
    *,
    on_site_started: SiteStartedFn | None = None,
    on_site_finished: SiteFinishedFn | None = None,
) -> list[ProductRow]:
    user_query = query.strip()
    site_plans = resolve_site_search_plans(user_query)
    rows: list[ProductRow] = []
    timeline_job_id = api_job_id.get() if api_job_id is not None else None
    per_site_timeout = 240.0
    with ThreadPoolExecutor(max_workers=SETTINGS.max_workers) as pool:
        futures: dict = {}
        submit_at: dict = {}
        for adapter in ALL_ADAPTERS:
            if on_site_started:
                on_site_started(adapter.display_name)
            f = pool.submit(
                _scrape_and_cleanup,
                adapter,
                site_plans[adapter.display_name],
                timeline_job_id=timeline_job_id,
            )
            futures[f] = adapter
            submit_at[f] = time.monotonic()
        remaining = set(futures.keys())

        while remaining:
            done, remaining = wait(remaining, timeout=1.0, return_when=FIRST_COMPLETED)
            for future in done:
                adapter = futures[future]
                try:
                    row = future.result()
                except Exception as e:
                    logger.exception("[%s] Worker failed: %s", adapter.display_name, e)
                    row = ProductRow.failed(adapter.display_name)
                rows.append(row)
                if on_site_finished:
                    on_site_finished(adapter.display_name, row)

            timed_out = {f for f in remaining if time.monotonic() - submit_at[f] > per_site_timeout}
            for future in timed_out:
                future.cancel()
                adapter = futures[future]
                logger.warning("[%s] Site timed out after %.0fs — marking unavailable", adapter.display_name, per_site_timeout)
                row = ProductRow.failed(adapter.display_name)
                rows.append(row)
                if on_site_finished:
                    on_site_finished(adapter.display_name, row)
                remaining.discard(future)

    # Stable column order matching site list
    order = {a.display_name: i for i, a in enumerate(ALL_ADAPTERS)}
    rows.sort(key=lambda r: order.get(r.website, 99))
    return rows


def rescrape_price_gap_outliers(
    rows: list[ProductRow],
    query: str,
    *,
    enabled: bool | None = None,
    on_recheck_begin: RecheckBeginFn | None = None,
    on_recheck_site: SiteFinishedFn | None = None,
) -> list[ProductRow]:
    """Re-run scrape when scraped price differs from LLM reference by more than threshold.

    Calls SETTINGS.openai_model with: "What the price in Amazon, Bestbuy, Walmart,
    Newegg for {query}", compares each successful scrape to that retailer's reference,
    and rescrapes once if relative gap exceeds threshold (default 20%).
    Skipped when the LLM benchmark fails or a retailer has no reference price.
    """
    use = SETTINGS.price_gap_rescrape_enabled if enabled is None else enabled
    if not use:
        return rows

    references = llm_reference_prices_for_query(query)
    if not references:
        return rows

    by_website = {a.display_name: a for a in ALL_ADAPTERS}
    thresh = SETTINGS.price_gap_rescrape_threshold
    outlier_indices: list[int] = []
    gap_notes: list[str] = []

    for i, row in enumerate(rows):
        if not row_has_scraped_price(row):
            continue
        found = parse_price(row.price)
        if found is None or found <= 0:
            continue
        ref = references.get(row.website)
        if ref is not None and ref > 0:
            gap = relative_price_gap(found, ref)
            if gap > thresh:
                outlier_indices.append(i)
                gap_notes.append(
                    f"{row.website} scraped=${found:,.2f} llm=${ref:,.2f} gap={gap * 100:.0f}%"
                )
            continue
        # No benchmark reference (e.g. Amazon=?). Per-row verify when site-level verify is off.
        if not SETTINGS.llm_price_verify_enabled:
            verify = llm_verify_scraped_price(
                user_query=query,
                product_title=row.product_title,
                scraped_price=found,
                retailer=row.website,
                source_url=row.source_url,
            )
            if not verify.plausible:
                outlier_indices.append(i)
                gap_notes.append(
                    f"{row.website} scraped=${found:,.2f} llm-verify rejected: {verify.reason}"
                )

    if not outlier_indices:
        logger.info(
            "Price-gap rescrape: all scraped prices within %.0f%% of LLM reference",
            thresh * 100,
        )
        return rows

    sites = [rows[i].website for i in outlier_indices]
    logger.info(
        "Price-gap rescrape (LLM %s): >%.0f%% from reference → retry: %s — %s",
        SETTINGS.openai_model,
        thresh * 100,
        ", ".join(sites),
        "; ".join(gap_notes),
    )

    if on_recheck_begin:
        on_recheck_begin(sites)

    site_plans = resolve_site_search_plans(query.strip())
    new_rows = list(rows)
    for i in outlier_indices:
        adapter = by_website.get(new_rows[i].website)
        if adapter is None:
            continue
        row = _scrape_and_cleanup(
            adapter,
            site_plans[adapter.display_name],
            timeline_job_id=api_job_id.get() if api_job_id is not None else None,
        )
        new_rows[i] = row
        if on_recheck_site:
            on_recheck_site(adapter.display_name, row)
    return new_rows
