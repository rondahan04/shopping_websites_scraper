"""Tracks when an LLM-backed check could not run, so the output can say so.

Every LLM call in this pipeline fails open: if the API is unreachable, out of
credits, or unconfigured, the caller accepts whatever it was asked to judge.
That default is deliberate — a scrape with no verification is more useful than
no scrape at all — but it is only honest if the run says the check did not
happen. Without that, a run against an exhausted API key produces output that
is indistinguishable from a fully verified one, and the failure is invisible
unless someone reads the logs line by line.

Components register here when they degrade; ``main.py`` prints the summary
under the results table and the API returns it with the job.
"""

from __future__ import annotations

import threading

# Component names, in the order they run, so a report reads like the pipeline.
SEARCH_PLAN = "search plan"
LISTING_EXTRACT = "listing extract"
TITLE_VERIFY = "title verify"
PRICE_VERIFY = "price verify"
PRICE_BENCHMARK = "price benchmark"
TRUST_SCORING = "trust scoring"

_ORDER = (
    SEARCH_PLAN,
    LISTING_EXTRACT,
    TITLE_VERIFY,
    PRICE_VERIFY,
    PRICE_BENCHMARK,
    TRUST_SCORING,
)

# What each component stops protecting against, in the output's terms.
_CONSEQUENCE = {
    SEARCH_PLAN: "per-retailer search terms fell back to the raw query",
    LISTING_EXTRACT: "listings parsed by selectors only, with no LLM fallback",
    TITLE_VERIFY: "listings accepted without checking they are the same product",
    PRICE_VERIFY: "prices accepted without checking they are the buy-box amount",
    PRICE_BENCHMARK: "no reference prices, so no outlier rescrape",
    TRUST_SCORING: "review-trust labels come from the heuristic, not the model",
}

_LOCK = threading.Lock()
_DEGRADED: dict[str, str] = {}


def _short(detail: str, limit: int = 160) -> str:
    collapsed = " ".join(str(detail).split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1] + "…"


def record_unavailable(component: str, detail: str) -> None:
    """Note that ``component`` could not run. The first reason per component wins.

    Called from worker threads (sites run in parallel), hence the lock. Keeping
    the first reason rather than the last avoids a single late timeout masking
    the real cause, which is usually the same for every call in a run.
    """
    with _LOCK:
        _DEGRADED.setdefault(component, _short(detail))


def degradations() -> dict[str, str]:
    """Degraded components → why, ordered by where they sit in the pipeline."""
    with _LOCK:
        found = dict(_DEGRADED)
    rank = {name: i for i, name in enumerate(_ORDER)}
    return dict(sorted(found.items(), key=lambda kv: (rank.get(kv[0], len(rank)), kv[0])))


def any_degraded() -> bool:
    with _LOCK:
        return bool(_DEGRADED)


def reset() -> None:
    """Clear state between runs. The CLI exits per run; the API server does not."""
    with _LOCK:
        _DEGRADED.clear()


def consequence(component: str) -> str:
    """What stopped being checked, phrased for someone reading the results."""
    return _CONSEQUENCE.get(component, "this check did not run")


def report_lines() -> list[str]:
    """Human-readable summary, empty when everything ran. Used by the CLI."""
    found = degradations()
    if not found:
        return []
    lines = [
        "WARNING: some checks did not run — results below are unverified, not verified-and-passed.",
    ]
    for component, detail in found.items():
        lines.append(f"  - {component}: {consequence(component)}")
        lines.append(f"      cause: {detail}")
    return lines
