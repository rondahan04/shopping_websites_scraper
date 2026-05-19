"""Scrape orchestration for HTTP handlers."""

from __future__ import annotations

import logging
from collections.abc import Callable

from models import ProductRow
from orchestrator import rescrape_price_gap_outliers, run_all_sites

logger = logging.getLogger(__name__)

SiteStartedFn = Callable[[str], None]
SiteFinishedFn = Callable[[str, ProductRow], None]
RecheckBeginFn = Callable[[list[str]], None]


def scrape_query(query: str, *, rescrape_price_gaps: bool = True) -> list[ProductRow]:
    """Run the same pipeline as the CLI (parallel sites + optional price-gap rescrape)."""
    return scrape_query_with_progress(
        query,
        rescrape_price_gaps=rescrape_price_gaps,
    )


def scrape_query_with_progress(
    query: str,
    *,
    rescrape_price_gaps: bool = True,
    on_first_pass_begin: Callable[[], None] | None = None,
    on_site_started: SiteStartedFn | None = None,
    on_site_finished: SiteFinishedFn | None = None,
    on_recheck_begin: RecheckBeginFn | None = None,
    on_recheck_site: SiteFinishedFn | None = None,
    on_wrapping_up: Callable[[], None] | None = None,
) -> list[ProductRow]:
    query = query.strip()
    if not query:
        raise ValueError("query is required")

    logger.info("API scrape started: %r", query)
    if on_first_pass_begin:
        on_first_pass_begin()

    rows = run_all_sites(query, on_site_started=on_site_started, on_site_finished=on_site_finished)

    if rescrape_price_gaps:
        rows = rescrape_price_gap_outliers(
            rows,
            query,
            on_recheck_begin=on_recheck_begin,
            on_recheck_site=on_recheck_site,
        )

    if on_wrapping_up:
        on_wrapping_up()

    logger.info(
        "API scrape finished: %d/%d sites with price",
        sum(1 for r in rows if r.status == "Success" and r.price != "N/A"),
        len(rows),
    )
    return rows
