"""Method 1: Scrapling fetch + BeautifulSoup parsing."""

from __future__ import annotations

from models import ExtractionFailure, ExtractionMethod, ProductFields
from sites.base import SiteAdapter
from utils.scrapling_fetch import fetch_html_scrapling
from validation.fields import validate_product_fields


def extract_with_scrapling(adapter: SiteAdapter, url: str) -> tuple[ProductFields, str]:
    patterns = adapter.bot_check_patterns()
    try:
        html, _ = fetch_html_scrapling(url, extra_patterns=patterns)
    except ExtractionFailure:
        raise
    except Exception as e:
        raise ExtractionFailure(str(e), ExtractionMethod.SCRAPLING) from e

    fields = adapter.parse_product(html, url)
    validate_product_fields(fields)
    return fields, html
