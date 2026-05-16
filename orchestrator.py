"""Parallel orchestration across all target sites."""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal

from config import SETTINGS
from models import ProductRow, row_has_scraped_price
from site_runner import scrape_site
from sites import ALL_ADAPTERS
from sites.base import SiteAdapter
from utils.parsing import parse_price

logger = logging.getLogger(__name__)


def _scrape_and_cleanup(adapter: SiteAdapter, query: str) -> ProductRow:
    """Scrape one site and tear down thread-local Playwright resources."""
    from extraction.playwright_extract import shutdown_browser
    from utils.http_fetch import close_http_session

    try:
        return scrape_site(adapter, query)
    finally:
        try:
            shutdown_browser()
        except Exception:
            pass
        try:
            close_http_session()
        except Exception:
            pass


SiteFinishedFn = Callable[[str, ProductRow], None]
RecheckBeginFn = Callable[[list[str]], None]


def run_all_sites(
    query: str,
    *,
    on_site_finished: SiteFinishedFn | None = None,
) -> list[ProductRow]:
    rows: list[ProductRow] = []
    with ThreadPoolExecutor(max_workers=SETTINGS.max_workers) as pool:
        futures = {
            pool.submit(_scrape_and_cleanup, adapter, query): adapter
            for adapter in ALL_ADAPTERS
        }
        for future in as_completed(futures):
            adapter: SiteAdapter = futures[future]
            try:
                row = future.result()
            except Exception as e:
                logger.exception("[%s] Worker failed: %s", adapter.display_name, e)
                row = ProductRow.failed(adapter.display_name)
            rows.append(row)
            if on_site_finished:
                on_site_finished(adapter.display_name, row)

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
    """Re-run scrape for sites whose successful price deviates more than ``threshold`` from the mean.

    Uses the arithmetic mean of all successful, positive prices. Requires at least
    ``price_gap_min_priced_sites`` priced rows. One rescrape pass only (no loop).
    """
    use = SETTINGS.price_gap_rescrape_enabled if enabled is None else enabled
    if not use:
        return rows

    by_website = {a.display_name: a for a in ALL_ADAPTERS}
    priced: list[tuple[int, Decimal]] = []
    for i, r in enumerate(rows):
        if not row_has_scraped_price(r):
            continue
        p = parse_price(r.price)
        if p is not None and p > 0:
            priced.append((i, p))

    min_n = SETTINGS.price_gap_min_priced_sites
    if len(priced) < min_n:
        logger.debug(
            "price-gap rescrape: need %d+ priced sites, have %d — skip",
            min_n,
            len(priced),
        )
        return rows

    total = sum(p for _, p in priced)
    n = len(priced)
    mean = total / n
    if mean <= 0:
        return rows

    mean_f = float(mean)
    thresh = SETTINGS.price_gap_rescrape_threshold
    outlier_indices: list[int] = []
    for i, p in priced:
        rel = abs(float(p) - mean_f) / mean_f
        if rel > thresh:
            outlier_indices.append(i)

    if not outlier_indices:
        return rows

    sites = [rows[i].website for i in outlier_indices]
    logger.info(
        "Price-gap rescrape: mean $%.2f from %d site(s); >%.0f%% from mean → retry: %s",
        mean_f,
        n,
        thresh * 100,
        ", ".join(sites),
    )

    if on_recheck_begin:
        on_recheck_begin(sites)

    new_rows = list(rows)
    for i in outlier_indices:
        adapter = by_website.get(new_rows[i].website)
        if adapter is None:
            continue
        row = _scrape_and_cleanup(adapter, query)
        new_rows[i] = row
        if on_recheck_site:
            on_recheck_site(adapter.display_name, row)
    return new_rows
