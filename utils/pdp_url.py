"""Lightweight PDP URL checks before extraction."""

from __future__ import annotations

import logging

import httpx

from config import SETTINGS

logger = logging.getLogger(__name__)


def pdp_url_reachable(url: str, *, timeout_s: float | None = None) -> bool:
    """Return False only when the PDP URL clearly does not exist (4xx).

    Timeouts and bot blocks are treated as reachable so extraction can try
    Firecrawl/Playwright; we only use this guard to drop hallucinated 404s.
    """
    if not url.startswith("http"):
        return False
    hdrs = {
        "User-Agent": SETTINGS.user_agent,
        "Referer": "https://www.google.com/",
    }
    timeout = float(timeout_s if timeout_s is not None else min(SETTINGS.product_timeout_s, 8.0))
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout, headers=hdrs) as client:
            resp = client.head(url)
            if resp.status_code in {403, 405, 411, 414, 415, 501} or resp.status_code >= 500:
                resp = client.get(url, timeout=timeout)
            if resp.status_code in {404, 410}:
                logger.info("PDP URL not reachable (%s): %s", resp.status_code, url[:120])
                return False
            return True
    except (httpx.TimeoutException, httpx.RequestError, OSError) as e:
        logger.debug("PDP URL check inconclusive for %s: %s", url[:120], e)
        return True
