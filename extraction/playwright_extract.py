"""Method 2: Playwright headless browser extraction."""

from __future__ import annotations

import threading
from typing import Any

from config import SETTINGS
from models import ExtractionFailure, ExtractionMethod, ProductFields
from sites.base import SiteAdapter
from validation.fields import is_bot_page, validate_product_fields

_thread_local = threading.local()


def _get_browser_context() -> tuple[Any, Any, Any]:
    """One Playwright browser per thread (safe for ThreadPoolExecutor)."""
    if getattr(_thread_local, "browser", None) is None:
        from playwright.sync_api import sync_playwright

        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        _thread_local.playwright = pw
        _thread_local.browser = browser
    return _thread_local.playwright, _thread_local.browser


def shutdown_browser() -> None:
    """Close all thread-local browsers; never raise on cleanup."""
    try:
        browser = getattr(_thread_local, "browser", None)
        pw = getattr(_thread_local, "playwright", None)
        if browser:
            browser.close()
        if pw:
            pw.stop()
    except Exception:
        pass
    _thread_local.browser = None
    _thread_local.playwright = None


def fetch_html_playwright(
    url: str,
    timeout_ms: int | None = None,
    *,
    strict_bot_check: bool = True,
) -> str:
    timeout_ms = timeout_ms or SETTINGS.playwright_timeout_ms
    _, browser = _get_browser_context()
    context = browser.new_context(
        user_agent=SETTINGS.user_agent,
        locale="en-US",
    )
    page = context.new_page()
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        if response and response.status in (403, 429):
            raise ExtractionFailure(f"http {response.status}", ExtractionMethod.PLAYWRIGHT)
        page.wait_for_timeout(2000)
        html = page.content()
    except ExtractionFailure:
        raise
    except Exception as e:
        raise ExtractionFailure(
            f"playwright navigation failed: {e}", ExtractionMethod.PLAYWRIGHT
        ) from e
    finally:
        context.close()

    if strict_bot_check and is_bot_page(html):
        raise ExtractionFailure("bot protection detected", ExtractionMethod.PLAYWRIGHT)
    return html


def extract_with_playwright(adapter: SiteAdapter, url: str) -> tuple[ProductFields, str]:
    html = fetch_html_playwright(url)
    if is_bot_page(html, adapter.bot_check_patterns()):
        raise ExtractionFailure("bot protection detected", ExtractionMethod.PLAYWRIGHT)
    fields = adapter.parse_product(html, url)
    validate_product_fields(fields)
    return fields, html
