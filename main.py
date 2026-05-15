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

from extraction.playwright_extract import shutdown_browser  # noqa: E402
from orchestrator import run_all_sites  # noqa: E402
from output.table import print_results_table  # noqa: E402


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
        rows = run_all_sites(query)
        print_results_table(rows)
        success = sum(1 for r in rows if r.status == "Success")
        return 0 if success >= 3 else 2
    finally:
        try:
            shutdown_browser()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
