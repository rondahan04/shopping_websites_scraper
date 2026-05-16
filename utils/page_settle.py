"""Post-navigation pause before reading page HTML (bot-detection mitigation)."""

from __future__ import annotations

import logging
import random
import time

from config import SETTINGS
from utils.human_behavior import random_settle_delay_s

logger = logging.getLogger(__name__)


def settle_after_page_load(*, context: str = "") -> None:
    """Random sleep in ``[settle_delay_min_s, settle_delay_max_s]`` after HTTP load."""
    delay = random_settle_delay_s()
    if delay <= 0:
        return
    if context:
        logger.debug("page settle %.2fs (%s)", delay, context)
    time.sleep(delay)


def firecrawl_wait_ms(requested_ms: int | None) -> int:
    """Firecrawl ``waitFor`` — random ms in configured range, honoring a higher floor."""
    low = int(SETTINGS.settle_delay_min_s * 1000)
    high = int(SETTINGS.settle_delay_max_s * 1000)
    if requested_ms is not None:
        high = max(high, requested_ms)
    if low > high:
        low, high = high, low
    return random.randint(low, high)
