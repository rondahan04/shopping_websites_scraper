"""HTTP fetch for M1 — httpx + BeautifulSoup parsers (replaces Scrapling/curl HTTP/2 path)."""

from __future__ import annotations

import logging
import httpx

from config import SETTINGS
from models import ExtractionFailure, ExtractionMethod
from validation.fields import is_bot_page

logger = logging.getLogger(__name__)


def fetch_html_http(
    url: str,
    timeout: float | None = None,
    *,
    extra_patterns: list[str] | None = None,
    proxy_url: str | None = None,
) -> tuple[str, int]:
    """GET HTML via httpx (HTTP/1.1). Optional proxy for US geo pricing."""
    timeout = timeout or SETTINGS.product_timeout_s
    headers = {
        "User-Agent": SETTINGS.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers=headers,
            proxy=proxy_url if proxy_url else None,
            http2=False,
        ) as client:
            resp = client.get(url)
        status = int(resp.status_code)
        if status in (403, 429):
            raise ExtractionFailure(f"http {status}", ExtractionMethod.HTTP)
        if status >= 400:
            raise ExtractionFailure(f"http {status}", ExtractionMethod.HTTP)
        html = resp.text
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
