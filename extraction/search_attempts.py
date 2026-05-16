"""Ordered retailer search strings for one scrape attempt."""

from __future__ import annotations

from extraction.llm_site_search_plan import SiteSearchPlan
from extraction.serp_fallback import enriched_search_queries


def search_attempt_queries(plan: SiteSearchPlan) -> list[str]:
    """Primary LLM search string, then heuristic variants from the canonical product name."""
    seen: set[str] = set()
    out: list[str] = []

    def add(q: str) -> None:
        key = q.strip().lower()
        if not key or key in seen:
            return
        seen.add(key)
        out.append(q.strip())

    add(plan.search_query)
    for variant in enriched_search_queries(plan.match_query):
        add(variant)
    for variant in enriched_search_queries(plan.user_query):
        add(variant)
    return out or [plan.user_query]
