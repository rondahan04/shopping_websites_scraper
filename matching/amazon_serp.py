"""Filter junk rows from Amazon search result pages before matching."""

from __future__ import annotations

import re

# Titles that are UI chrome, not products.
_AMAZON_JUNK_TITLE_RE = re.compile(
    r"^\s*("
    r"see\s+options?"
    r"|see\s+all\s+"
    r"|shop\s+now"
    r"|more\s+results"
    r"|sponsored"
    r")\s*$",
    re.I,
)

# Price-only or currency-heavy titles (wrong locale / broken card parse).
_AMAZON_PRICE_ONLY_RE = re.compile(
    r"^\s*(?:"
    r"(?:ILS|USD|EUR|GBP|CAD|\$|€|£)\s*[\d,.\s]+"
    r"|(?:[\d,]+\.?\d*)\s*(?:ILS|USD|EUR|GBP|CAD)"
    r")\s*$",
    re.I,
)

_MIN_TITLE_LEN = 12


def is_amazon_serp_junk_title(title: str) -> bool:
    """Drop Amazon SERP rows that are not real product titles."""
    t = " ".join(title.split()).strip()
    if len(t) < _MIN_TITLE_LEN:
        return True
    if _AMAZON_JUNK_TITLE_RE.match(t):
        return True
    if _AMAZON_PRICE_ONLY_RE.match(t):
        return True
    # "ILS66.93ILS66.93" / "Typical: ILS 43.72" style glitches
    if re.search(r"(ILS|USD|EUR)\s*[\d,.]+", t, re.I) and not re.search(
        r"[a-z]{4,}", t, re.I
    ):
        return True
    if re.search(r"\btypical:\s*(ILS|USD)", t, re.I):
        return True
    if t.count("ILS") >= 2 and "headphone" not in t.lower() and "bose" not in t.lower():
        return True
    return False
