"""Detect non-new retail conditions in listing titles (renewed, refurb, open-box)."""

from __future__ import annotations

import re

_NON_NEW_RE = re.compile(
    r"\b("
    r"renewed(?:\s+premium)?"
    r"|refurb(?:ished)?"
    r"|open[-\s]?box"
    r"|pre[-\s]?owned"
    r"|used\s*[-–]?\s*"
    r"|certified\s+refurbished"
    r")\b",
    re.I,
)

_USED_QUERY_RE = re.compile(
    r"\b(renewed|refurb(?:ished)?|open[-\s]?box|pre[-\s]?owned|used)\b",
    re.I,
)


def query_requests_used_condition(query: str) -> bool:
    """True when the user explicitly asked for used / renewed / open-box listings."""
    return bool(_USED_QUERY_RE.search(query or ""))


def listing_is_non_new(title: str) -> bool:
    """True when the visible title advertises a non-new condition."""
    return bool(_NON_NEW_RE.search(title or ""))


def condition_score_penalty(query: str, title: str) -> float:
    """Points to subtract from SERP match score when preferring new retail."""
    if query_requests_used_condition(query):
        return 0.0
    if listing_is_non_new(title):
        return 22.0
    return 0.0
