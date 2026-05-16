"""Stage 2 — browser-based scraping: Playwright headless browser + BeautifulSoup."""

from __future__ import annotations

import threading
from typing import Any
from urllib.parse import urlparse

from config import SETTINGS
from models import ExtractionFailure, ExtractionMethod, ProductFields
from sites.base import SiteAdapter
from utils.browser_profiles import build_http_headers, pick_browser_profile
from utils.human_behavior import humanize_after_navigation
from validation.fields import is_bot_page, validate_product_fields

_thread_local = threading.local()


def _get_browser_context() -> tuple[Any, Any, Any]:
    """One Playwright browser per thread (safe for ThreadPoolExecutor)."""
    if getattr(_thread_local, "browser", None) is None:
        from playwright.sync_api import sync_playwright

        try:
            pw = sync_playwright().start()
            browser = pw.chromium.launch(headless=True)
        except Exception as e:
            msg = (
                "playwright launch failed — run `cd shopping_websites_scraper && "
                "playwright install chromium` (or unset PLAYWRIGHT_BROWSERS_PATH to use default)."
            )
            raise ExtractionFailure(f"{msg} ({e})", ExtractionMethod.PLAYWRIGHT) from e
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


def _referer_for_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}/"
    return "https://www.google.com/"


def fetch_html_playwright(
    url: str,
    timeout_ms: int | None = None,
    *,
    strict_bot_check: bool = True,
    ready_selectors: list[str] | tuple[str, ...] | None = None,
) -> str:
    timeout_ms = timeout_ms or SETTINGS.playwright_timeout_ms
    _, browser = _get_browser_context()
    profile = pick_browser_profile()
    referer = _referer_for_url(url)
    extra_headers = build_http_headers(profile, referer=referer)
    # Playwright sets User-Agent via context; pass the rest as extra HTTP headers.
    extra_http = {k: v for k, v in extra_headers.items() if k.lower() != "user-agent"}
    context = browser.new_context(
        user_agent=profile.user_agent,
        locale=profile.accept_language.split(",")[0].strip() or "en-US",
        extra_http_headers=extra_http,
        viewport={"width": 1366, "height": 768},
    )
    page = context.new_page()
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        if response and response.status in (403, 429):
            raise ExtractionFailure(f"http {response.status}", ExtractionMethod.PLAYWRIGHT)
        humanize_after_navigation(
            page,
            ready_selectors=ready_selectors,
            timeout_ms=min(timeout_ms, 20_000),
        )
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


def extract_with_playwright(
    adapter: SiteAdapter,
    url: str,
) -> tuple[ProductFields, str]:
    html = fetch_html_playwright(url, ready_selectors=adapter.page_ready_selectors())
    if is_bot_page(html, adapter.bot_check_patterns()):
        raise ExtractionFailure("bot protection detected", ExtractionMethod.PLAYWRIGHT)
    fields = adapter.parse_product(html, url)
    validate_product_fields(fields)
    return fields, html
