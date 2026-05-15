"""HTTP fetch helpers with thread-local connection pooling."""

from __future__ import annotations

import threading

import httpx

from config import SETTINGS
from models import ExtractionFailure, ExtractionMethod
from validation.fields import is_bot_page

_thread_local = threading.local()


def _get_client() -> httpx.Client:
    client = getattr(_thread_local, "http_client", None)
    if client is None:
        client = httpx.Client(
            follow_redirects=True,
            timeout=SETTINGS.product_timeout_s,
            headers={
                "User-Agent": SETTINGS.user_agent,
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        _thread_local.http_client = client
    return client


def close_http_client() -> None:
    client = getattr(_thread_local, "http_client", None)
    if client is not None:
        try:
            client.close()
        except Exception:
            pass
        _thread_local.http_client = None


def fetch_url(
    url: str,
    timeout: float | None = None,
    *,
    extra_patterns: list[str] | None = None,
) -> tuple[str, int]:
    timeout = timeout or SETTINGS.product_timeout_s
    client = _get_client()
    try:
        resp = client.get(url, timeout=timeout)
    except httpx.TimeoutException as e:
        raise ExtractionFailure(f"timeout: {e}", ExtractionMethod.REQUESTS) from e
    except httpx.HTTPError as e:
        raise ExtractionFailure(f"http error: {e}", ExtractionMethod.REQUESTS) from e

    if resp.status_code in (403, 429):
        raise ExtractionFailure(f"http {resp.status_code}", ExtractionMethod.REQUESTS)
    if resp.status_code >= 400:
        raise ExtractionFailure(f"http {resp.status_code}", ExtractionMethod.REQUESTS)

    html = resp.text
    if is_bot_page(html, extra_patterns):
        raise ExtractionFailure("bot protection detected", ExtractionMethod.REQUESTS)
    return html, resp.status_code
