"""Stage 1 HTTP fetch — httpx (requests-style) for BeautifulSoup parsers."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx

from config import SETTINGS
from models import ExtractionFailure, ExtractionMethod
from utils.browser_profiles import build_http_headers, pick_browser_profile
from utils.page_settle import settle_after_page_load
from validation.fields import is_bot_page

logger = logging.getLogger(__name__)


def _default_referer(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}/"
    return "https://www.google.com/"


def fetch_html_http(
    url: str,
    timeout: float | None = None,
    *,
    extra_patterns: list[str] | None = None,
    settle_after_load: bool = False,
    referer: str | None = None,
) -> tuple[str, int]:
    """GET HTML via httpx (HTTP/1.1) with rotated browser-like headers."""
    timeout = timeout or SETTINGS.product_timeout_s
    profile = pick_browser_profile()
    headers = build_http_headers(profile, referer=referer or _default_referer(url))
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers=headers,
            http2=False,
        ) as client:
            resp = client.get(url)
        status = int(resp.status_code)
        if status in (403, 429):
            raise ExtractionFailure(f"http {status}", ExtractionMethod.HTTP)
        if status >= 400:
            raise ExtractionFailure(f"http {status}", ExtractionMethod.HTTP)
        html = resp.text
        if settle_after_load:
            settle_after_page_load(context=url)
        if is_bot_page(html, extra_patterns):
            raise ExtractionFailure("bot protection detected", ExtractionMethod.HTTP)
        return html, status
    except ExtractionFailure:
        raise
    except Exception as e:
        logger.debug("HTTP fetch error for %s: %s", url, e)
        raise ExtractionFailure(str(e), ExtractionMethod.HTTP) from e


def close_http_session() -> None:
    """No persistent session; kept for orchestrator cleanup symmetry."""
    return None
