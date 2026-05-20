"""Stage 1 HTTP fetch — curl_cffi with full Chrome TLS + header impersonation."""

from __future__ import annotations

import logging
import random
from urllib.parse import urlparse

from curl_cffi import CurlHttpVersion
from curl_cffi.requests import Session

from config import SETTINGS
from models import ExtractionFailure, ExtractionMethod
from utils.page_settle import settle_after_page_load
from validation.fields import is_bot_page

logger = logging.getLogger(__name__)

# Rotate across recent stable Chrome builds to vary TLS fingerprint.
_IMPERSONATE_TARGETS = (
    "chrome136",
    "chrome131",
    "chrome124",
    "chrome120",
)


def _default_referer(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}/"
    return "https://www.google.com/"


def _is_bestbuy_url(url: str) -> bool:
    return "bestbuy.com" in urlparse(url).netloc


def fetch_html_http(
    url: str,
    timeout: float | None = None,
    *,
    extra_patterns: list[str] | None = None,
    settle_after_load: bool = False,
    referer: str | None = None,
    warm_homepage: bool = False,
) -> tuple[str, int]:
    """GET HTML via curl_cffi with Chrome TLS fingerprint + full Sec-Ch/Sec-Fetch headers."""
    timeout = timeout or SETTINGS.product_timeout_s
    impersonate = random.choice(_IMPERSONATE_TARGETS)
    extra_headers: dict[str, str] = {}
    if referer:
        extra_headers["Referer"] = referer or _default_referer(url)
    # BestBuy's CDN rejects HTTP/2 connections from non-browser IPs; force HTTP/1.1.
    http_version = CurlHttpVersion.V1_1 if _is_bestbuy_url(url) else CurlHttpVersion.V2TLS
    try:
        with Session(impersonate=impersonate) as session:
            if warm_homepage:
                parsed = urlparse(url)
                homepage = f"{parsed.scheme}://{parsed.netloc}/"
                try:
                    session.get(homepage, timeout=min(float(timeout), 8.0), allow_redirects=True)
                except Exception:
                    pass
            resp = session.get(
                url,
                headers=extra_headers,
                timeout=timeout,
                allow_redirects=True,
                http_version=http_version,
            )
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
