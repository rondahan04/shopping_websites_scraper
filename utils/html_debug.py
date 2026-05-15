"""Optional save of SERP and product HTML for manual inspection / testing."""

from __future__ import annotations

import re
from pathlib import Path

_debug_dir: Path | None = None


def set_html_debug_dir(path: Path | None) -> None:
    global _debug_dir
    _debug_dir = Path(path).resolve() if path else None


def get_html_debug_dir() -> Path | None:
    return _debug_dir


def site_slug(display_name: str) -> str:
    s = display_name.lower().replace(".", "").replace(" ", "_")
    s = re.sub(r"[^a-z0-9_]+", "", s)
    return s or "site"


def write_site_html(display_name: str, kind: str, html: str) -> str:
    """Write UTF-8 HTML; kind is e.g. ``serp`` or ``product``."""
    if _debug_dir is None:
        raise RuntimeError("html debug dir not set")
    _debug_dir.mkdir(parents=True, exist_ok=True)
    slug = site_slug(display_name)
    path = _debug_dir / f"{slug}_{kind}.html"
    path.write_text(html, encoding="utf-8", errors="replace")
    return str(path)
