#!/usr/bin/env python3
"""Fault-tolerant multi-site e-commerce price scraper."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path when run as script
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from extraction import llm_health  # noqa: E402
from extraction.playwright_extract import shutdown_browser  # noqa: E402
from models import row_has_scraped_price  # noqa: E402
from orchestrator import rescrape_price_gap_outliers, run_all_sites  # noqa: E402
from output.table import print_results_table  # noqa: E402
from utils.html_debug import set_html_debug_dir  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Search Amazon, Best Buy, Walmart, and Newegg for a product and compare prices.",
    )
    parser.add_argument(
        "query",
        nargs="?",
        help='Product search query, e.g. "Lenovo Tab P12-2024"',
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress info logs",
    )
    parser.add_argument(
        "--save-html",
        type=Path,
        metavar="DIR",
        help="Write per-site SERP and product HTML under DIR (e.g. ./debug_html) for debugging parsers",
    )
    parser.add_argument(
        "--no-price-gap-rescrape",
        action="store_true",
        help="Disable second pass: rescrape sites whose price is >20%% (configurable) from GPT reference prices",
    )
    args = parser.parse_args()

    query = args.query
    if not query:
        query = input("Enter product search query: ").strip()
    if not query:
        print("Error: query is required.", file=sys.stderr)
        return 1

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    try:
        if args.save_html:
            set_html_debug_dir(args.save_html)
        llm_health.reset()
        rows = run_all_sites(query)
        rows = rescrape_price_gap_outliers(rows, query, enabled=not args.no_price_gap_rescrape)
        print_results_table(rows)
        # Printed under the table, not logged: a run whose verification passes
        # never fired still produces a table that looks fully checked, and
        # -q suppresses the warnings that would have said otherwise.
        for line in llm_health.report_lines():
            print(line, file=sys.stderr)
        success = sum(1 for r in rows if row_has_scraped_price(r))
        return 0 if success >= 3 else 2
    finally:
        set_html_debug_dir(None)
        try:
            shutdown_browser()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
