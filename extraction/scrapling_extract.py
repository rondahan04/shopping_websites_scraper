"""Method 1: HTTP fetch (httpx) + BeautifulSoup parsing."""

from __future__ import annotations

from models import ExtractionFailure, ExtractionMethod, ProductFields
from sites.base import SiteAdapter
from utils.http_fetch import fetch_html_http
from validation.fields import validate_product_fields


def extract_with_http(
    adapter: SiteAdapter,
    url: str,
    *,
    proxy_url: str | None = None,
) -> tuple[ProductFields, str]:
    patterns = adapter.bot_check_patterns()
    try:
        html, _ = fetch_html_http(url, extra_patterns=patterns, proxy_url=proxy_url)
    except ExtractionFailure:
        raise
    except Exception as e:
        raise ExtractionFailure(str(e), ExtractionMethod.HTTP) from e

    fields = adapter.parse_product(html, url)
    validate_product_fields(fields)
    return fields, html


def extract_with_scrapling(
    adapter: SiteAdapter,
    url: str,
    *,
    proxy_url: str | None = None,
) -> tuple[ProductFields, str]:
    """Backward-compatible name; M1 is httpx + BeautifulSoup, not Scrapling."""
    return extract_with_http(adapter, url, proxy_url=proxy_url)
