"""Rotating realistic browser profiles (User-Agent + companion headers)."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class BrowserProfile:
    user_agent: str
    accept_language: str
    platform: str  # Playwright device hint: "Win32", "MacIntel", etc.


# Modern desktop Chrome / Safari / Edge on Windows 11 and macOS.
_BROWSER_PROFILES: tuple[BrowserProfile, ...] = (
    BrowserProfile(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        accept_language="en-US,en;q=0.9",
        platform="Win32",
    ),
    BrowserProfile(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0"
        ),
        accept_language="en-US,en;q=0.9",
        platform="Win32",
    ),
    BrowserProfile(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        accept_language="en-US,en;q=0.9",
        platform="MacIntel",
    ),
    BrowserProfile(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/18.2 Safari/605.1.15"
        ),
        accept_language="en-US,en;q=0.9",
        platform="MacIntel",
    ),
    BrowserProfile(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) "
            "Gecko/20100101 Firefox/133.0"
        ),
        accept_language="en-US,en;q=0.9",
        platform="Win32",
    ),
    BrowserProfile(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_1) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        ),
        accept_language="en-US,en;q=0.9,he;q=0.8",
        platform="MacIntel",
    ),
)

_DEFAULT_ACCEPT = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8"
)


def pick_browser_profile() -> BrowserProfile:
    """Return a random profile from the pool."""
    return random.choice(_BROWSER_PROFILES)


def build_http_headers(
    profile: BrowserProfile | None = None,
    *,
    referer: str | None = None,
) -> dict[str, str]:
    """Headers that mirror a full browser request (not User-Agent alone)."""
    p = profile or pick_browser_profile()
    headers: dict[str, str] = {
        "User-Agent": p.user_agent,
        "Accept": _DEFAULT_ACCEPT,
        "Accept-Language": p.accept_language,
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
    }
    if referer:
        headers["Referer"] = referer
    return headers
