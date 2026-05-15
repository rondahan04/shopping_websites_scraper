"""Price-mean gap rescrape orchestration."""

from __future__ import annotations

from unittest.mock import patch

from models import ProductRow
from orchestrator import rescrape_price_gap_outliers


def _row(site: str, price: str, status: str = "Success") -> ProductRow:
    return ProductRow(
        website=site,
        product_title="Test",
        price=price,
        status=status,  # type: ignore[arg-type]
        method="scrapling",
    )


def test_rescrape_skipped_when_disabled():
    rows = [
        _row("Amazon.com", "$100.00"),
        _row("Walmart.com", "$500.00"),
    ]
    out = rescrape_price_gap_outliers(rows, "q", enabled=False)
    assert out == rows


def test_rescrape_skipped_when_only_one_priced_site():
    rows = [
        _row("Amazon.com", "$100.00"),
        ProductRow.failed("Walmart.com"),
    ]
    out = rescrape_price_gap_outliers(rows, "q", enabled=True)
    assert out[0].price == rows[0].price


def test_rescrape_skipped_when_prices_within_threshold():
    rows = [
        _row("Amazon.com", "$100.00"),
        _row("Walmart.com", "$105.00"),
    ]
    out = rescrape_price_gap_outliers(rows, "q", enabled=True)
    assert out == rows


def test_rescrapes_sites_beyond_threshold_from_mean():
    rows = [
        _row("Amazon.com", "$100.00"),
        _row("BestBuy.com", "$100.00"),
        _row("Walmart.com", "$200.00"),
        _row("Newegg.com", "$100.00"),
    ]
    # mean = 125; Walmart 200 → |200-125|/125 = 0.6 > 0.30

    def fake_scrape(adapter, query: str) -> ProductRow:
        return ProductRow(
            website=adapter.display_name,
            product_title="Re",
            price="$125.00",
            status="Success",
            method="playwright",
        )

    with patch("orchestrator._scrape_and_cleanup", side_effect=fake_scrape):
        out = rescrape_price_gap_outliers(rows, "tablet", enabled=True)

    walmart = next(r for r in out if r.website == "Walmart.com")
    assert walmart.price == "$125.00"
    assert walmart.method == "playwright"
    amazon = next(r for r in out if r.website == "Amazon.com")
    assert amazon.price == "$100.00"


def test_mean_uses_only_success_rows():
    rows = [
        _row("Amazon.com", "$100.00"),
        ProductRow.failed("BestBuy.com"),
        _row("Walmart.com", "$100.00"),
        _row("Newegg.com", "$200.00"),
    ]

    calls: list[str] = []

    def fake_scrape(adapter, query: str) -> ProductRow:
        calls.append(adapter.display_name)
        return ProductRow(
            website=adapter.display_name,
            product_title="X",
            price="$133.00",
            status="Success",
            method="llm",
        )

    with patch("orchestrator._scrape_and_cleanup", side_effect=fake_scrape):
        rescrape_price_gap_outliers(rows, "q", enabled=True)

    assert "Newegg.com" in calls
    assert len(calls) == 1
