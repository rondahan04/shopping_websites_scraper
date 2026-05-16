"""Resolve Amazon PDP path after redirects (SERP anchors often omit the pretty slug)."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx

from config import SETTINGS
from utils.browser_profiles import build_http_headers, pick_browser_profile

logger = logging.getLogger(__name__)


def amazon_resolved_product_path(candidate_url: str) -> str | None:
    """Return ``urlparse(final_url).path`` after following redirects, or ``None``.

    Needed because search tiles often advertise ``/dp/ASIN/ref=…`` without the slug
    that reveals ``…/Apple-MacBook-Memory-…/dp/…`` RAM SKUs after redirect.
    """
    hdrs = build_http_headers(pick_browser_profile(), referer="https://www.google.com/")
    timeout = float(min(max(SETTINGS.product_timeout_s, 6.0), 15.0))
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout, headers=hdrs) as c:
            resp = c.head(candidate_url)
            if resp.status_code in {403, 405, 411, 414, 415, 501} or resp.status_code >= 500:
                resp = c.get(candidate_url)
            if resp.status_code >= 400:
                logger.debug(
                    "amazon_resolve: non-HTTP2xx for %s status=%s", candidate_url, resp.status_code
                )
                return None
            final = str(resp.url)
            path = urlparse(final).path
            if "/dp/" in path or "/gp/product/" in path:
                return path
    except (httpx.TimeoutException, httpx.RequestError, OSError):
        logger.debug("amazon_resolve: request failed for %s", candidate_url, exc_info=True)
    return None
