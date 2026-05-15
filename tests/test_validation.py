"""Tests for field validation."""

from decimal import Decimal

import pytest

from models import ExtractionFailure, ProductFields
from validation.fields import is_bot_page, validate_product_fields


def test_validate_accepts_title_and_price_only():
    fields = ProductFields(
        title="Lenovo Tab P12",
        price=Decimal("499.99"),
        average_rating=None,
        review_count=None,
    )
    validate_product_fields(fields)


def test_validate_rejects_missing_price():
    fields = ProductFields(title="Lenovo Tab P12", price=None, average_rating=4.5, review_count=10)
    with pytest.raises(ExtractionFailure, match="missing price"):
        validate_product_fields(fields)


def test_validate_rejects_generic_title():
    fields = ProductFields(title="Access Denied", price=Decimal("1.00"), average_rating=None, review_count=None)
    with pytest.raises(ExtractionFailure):
        validate_product_fields(fields)


def test_is_bot_page_detects_captcha():
    assert is_bot_page("<html>Please complete the captcha</html>")
