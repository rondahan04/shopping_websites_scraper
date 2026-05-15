"""Method 1: requests + BeautifulSoup extraction."""

from __future__ import annotations

from models import ExtractionFailure, ExtractionMethod, ProductFields
from sites.base import SiteAdapter
from utils.http_client import fetch_url
from validation.fields import validate_product_fields


def extract_with_requests(adapter: SiteAdapter, url: str) -> ProductFields:
    html, _ = fetch_url(url, extra_patterns=adapter.bot_check_patterns())
    fields = adapter.parse_product(html, url)
    validate_product_fields(fields)
    return fields
