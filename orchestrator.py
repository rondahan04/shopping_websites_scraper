"""Parallel orchestration across all target sites."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import SETTINGS
from models import ProductRow
from site_runner import scrape_site
from sites import ALL_ADAPTERS
from sites.base import SiteAdapter

logger = logging.getLogger(__name__)


def _scrape_and_cleanup(adapter: SiteAdapter, query: str) -> ProductRow:
    """Scrape one site and tear down thread-local Playwright resources."""
    from extraction.playwright_extract import shutdown_browser
    from utils.scrapling_fetch import close_scrapling_session

    try:
        return scrape_site(adapter, query)
    finally:
        try:
            shutdown_browser()
        except Exception:
            pass
        try:
            close_scrapling_session()
        except Exception:
            pass


def run_all_sites(query: str) -> list[ProductRow]:
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

    # Stable column order matching site list
    order = {a.display_name: i for i, a in enumerate(ALL_ADAPTERS)}
    rows.sort(key=lambda r: order.get(r.website, 99))
    return rows
