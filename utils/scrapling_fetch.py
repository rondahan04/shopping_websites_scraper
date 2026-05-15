"""Scrapling Fetcher (HTTP) for M1 — no in-process browser (avoids asyncio + sync Playwright conflicts in thread pools)."""

from __future__ import annotations

import logging

from config import SETTINGS
from models import ExtractionFailure, ExtractionMethod
from validation.fields import is_bot_page

logger = logging.getLogger(__name__)


def _response_html(page) -> str:
    return str(page.html_content)


def close_scrapling_session() -> None:
    """No persistent session; kept for orchestrator cleanup symmetry."""
    return None


def fetch_html_scrapling(
    url: str,
    timeout: float | None = None,
    *,
    extra_patterns: list[str] | None = None,
) -> tuple[str, int]:
    """TLS-impersonating HTTP fetch via Scrapling; bot/captcha pages fall through to M2 Playwright."""
    timeout = timeout or SETTINGS.product_timeout_s
    from scrapling.fetchers import Fetcher

    try:
        page = Fetcher.get(
            url,
            impersonate="chrome",
            stealthy_headers=True,
            timeout=timeout,
        )
        status = int(getattr(page, "status", 0) or 0)
        if status in (403, 429):
            raise ExtractionFailure(f"http {status}", ExtractionMethod.SCRAPLING)
        if status >= 400:
            raise ExtractionFailure(f"http {status}", ExtractionMethod.SCRAPLING)
        html = _response_html(page)
        if is_bot_page(html, extra_patterns):
            raise ExtractionFailure("bot protection detected", ExtractionMethod.SCRAPLING)
        return html, status
    except ExtractionFailure:
        raise
    except Exception as e:
        logger.debug("Scrapling Fetcher error for %s: %s", url, e)
        raise ExtractionFailure(str(e), ExtractionMethod.SCRAPLING) from e
