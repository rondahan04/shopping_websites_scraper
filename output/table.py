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
            r.status,
            r.method,
        ]
        for r in rows
    ]
    print(tabulate(table_rows, headers=COLUMNS, tablefmt="simple"))
    success = sum(1 for r in rows if r.status == "Success")
    print(f"\nSucceeded: {success}/{len(rows)} (target: at least 3 of 4)")


def _truncate(text: str, max_len: int) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
