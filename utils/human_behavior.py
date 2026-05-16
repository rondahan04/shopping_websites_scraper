"""Human-like delays, scrolling, and DOM-ready waits for browser automation."""

from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING, Any

from config import SETTINGS

if TYPE_CHECKING:
    from playwright.sync_api import Page

logger = logging.getLogger(__name__)

# First matching selector wins (explicit wait instead of blind sleep).
DEFAULT_PAGE_READY_SELECTORS: tuple[str, ...] = (
    "main",
    "h1",
    "#productTitle",
    "[data-testid='product-title']",
    ".sku-title",
    "[itemprop='name']",
    "#search",
    "[role='search']",
)


def random_settle_delay_s() -> float:
    """Random pause in ``[settle_delay_min_s, settle_delay_max_s]``."""
    return random.uniform(SETTINGS.settle_delay_min_s, SETTINGS.settle_delay_max_s)


def wait_for_page_ready(
    page: Page,
    selectors: list[str] | tuple[str, ...] | None,
    *,
    timeout_ms: int,
) -> str | None:
    """Wait until any selector is attached; return the one that matched."""
    candidates = list(selectors) if selectors else list(DEFAULT_PAGE_READY_SELECTORS)
    if not candidates:
        return None
    budget = max(3000, timeout_ms)
    per_selector = max(1500, budget // len(candidates))
    for sel in candidates:
        try:
            page.wait_for_selector(sel, state="attached", timeout=per_selector)
            logger.debug("page ready via selector %s", sel)
            return sel
        except Exception:
            continue
    logger.debug("page ready: no selector matched within budget")
    return None


def simulate_human_on_page(page: Page) -> None:
    """Random scroll + mouse movement before reading DOM."""
    viewport = page.viewport_size or {"width": 1280, "height": 720}
    width = int(viewport.get("width", 1280))
    height = int(viewport.get("height", 720))

    scroll_passes = random.randint(1, 3)
    for _ in range(scroll_passes):
        delta_y = random.randint(80, min(600, max(120, height // 3)))
        page.evaluate("(y) => window.scrollBy(0, y)", delta_y)
        page.wait_for_timeout(random.randint(200, 700))

    x = random.randint(40, max(80, width - 40))
    y = random.randint(40, max(80, height - 40))
    steps = random.randint(6, 18)
    page.mouse.move(x, y, steps=steps)
    page.wait_for_timeout(random.randint(150, 500))

    if random.random() < 0.4:
        page.evaluate("(y) => window.scrollBy(0, y)", random.randint(-200, 120))
        page.wait_for_timeout(random.randint(100, 350))


def humanize_after_navigation(
    page: Page,
    *,
    ready_selectors: list[str] | tuple[str, ...] | None = None,
    timeout_ms: int,
) -> None:
    """Explicit DOM wait, light interaction, then a random settle pause."""
    wait_for_page_ready(page, ready_selectors, timeout_ms=timeout_ms)
    simulate_human_on_page(page)
    delay_s = random_settle_delay_s()
    if delay_s > 0:
        page.wait_for_timeout(int(delay_s * 1000))
