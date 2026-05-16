"""Console table formatting."""

from __future__ import annotations

from models import ProductRow
from tabulate import tabulate

COLUMNS = [
    "Website",
    "Product title",
    "Price",
    "Average rating",
    "Review count",
    "Source URL",
    "Status",
    "Method",
]


def print_results_table(rows: list[ProductRow]) -> None:
    table_rows = [
        [
            r.website,
            _truncate(r.product_title, 60),
            r.price,
            r.average_rating,
            r.review_count,
            r.source_url,
            r.status,
            r.method,
        ]
        for r in rows
    ]
    print(tabulate(table_rows, headers=COLUMNS, tablefmt="simple"))
    success = sum(1 for r in rows if r.status == "Success")
    print(f"\nSucceeded: {success}/{len(rows)} (target: at least 3 of 4)")

    debug_rows = [r for r in rows if r.serp_html_path or r.product_html_path]
    if debug_rows:
        print("\nSaved HTML (--save-html):")
        for r in debug_rows:
            parts = [r.website]
            if r.serp_html_path:
                parts.append(f"SERP: {r.serp_html_path}")
            if r.product_html_path:
                parts.append(f"product: {r.product_html_path}")
            print("  " + " | ".join(parts))


def _truncate(text: str, max_len: int) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
