"""Extraction pipeline tests with mocked fetch."""

from decimal import Decimal
from unittest.mock import patch

from extraction.pipeline import run_extraction_pipeline
from models import ExtractionFailure, ExtractionMethod, ProductFields
from sites.amazon import AmazonAdapter


def test_pipeline_succeeds_on_m1():
    adapter = AmazonAdapter()
    fields = ProductFields(
        title="Lenovo Tab P12",
        price=Decimal("499.99"),
        average_rating=None,
        review_count=None,
    )

    with patch("extraction.pipeline.extract_with_requests", return_value=fields):
        row = run_extraction_pipeline(adapter, "https://www.amazon.com/dp/B0TEST")

    assert row.status == "Success"
    assert row.method == ExtractionMethod.REQUESTS.value
    assert row.price == "$499.99"
    assert row.average_rating == "N/A"


def test_pipeline_falls_through_to_m2():
    adapter = AmazonAdapter()
    fields = ProductFields(
        title="Lenovo Tab P12",
        price=Decimal("499.99"),
        average_rating=4.5,
        review_count=100,
    )

    with (
        patch("extraction.pipeline.extract_with_requests", side_effect=ExtractionFailure("blocked")),
        patch("extraction.pipeline.extract_with_playwright", return_value=(fields, "<html/>")),
    ):
        row = run_extraction_pipeline(adapter, "https://www.amazon.com/dp/B0TEST")

    assert row.status == "Success"
    assert row.method == ExtractionMethod.PLAYWRIGHT.value
