"""Per-retailer search strings and canonical product names from GPT."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from config import SETTINGS

logger = logging.getLogger(__name__)

# ProductRow.website → JSON keys from the model.
_SITE_JSON_KEYS: dict[str, tuple[str, ...]] = {
    "Amazon.com": ("amazon",),
    "BestBuy.com": ("bestbuy", "best_buy", "best buy"),
    "Walmart.com": ("walmart",),
    "Newegg.com": ("newegg", "new_egg"),
}

_PLAN_SYSTEM = """You optimize product searches on US e-commerce sites.
The user gives an informal product query. For each retailer, suggest:
1. search_query — short text to paste into that site's search box (include model numbers and official naming retailers use).
2. product_name — full canonical product name for matching the correct listing (the main device, not cases, earpads, chargers, or other accessories).

Return ONLY valid JSON with keys amazon, bestbuy, walmart, newegg. Each value is an object:
{"search_query": "...", "product_name": "..."}
Use strings only. Do not include accessories unless the user explicitly asked for one."""


@dataclass(frozen=True)
class SiteSearchPlan:
    """How to search one retailer and which product name to match against SERP/PDP titles."""

    user_query: str
    search_query: str
    match_query: str

    @classmethod
    def passthrough(cls, user_query: str) -> SiteSearchPlan:
        q = user_query.strip()
        return cls(user_query=q, search_query=q, match_query=q)


def _normalize_key(key: str) -> str:
    return "".join(ch for ch in key.lower() if ch.isalnum())


def _coerce_str(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_site_entry(entry: object, fallback: str) -> tuple[str, str]:
    if isinstance(entry, str):
        s = _coerce_str(entry)
        return s or fallback, s or fallback
    if isinstance(entry, dict):
        search = _coerce_str(entry.get("search_query") or entry.get("search") or entry.get("query"))
        product = _coerce_str(
            entry.get("product_name") or entry.get("product") or entry.get("name") or entry.get("title")
        )
        if not search:
            search = product or fallback
        if not product:
            product = search or fallback
        return search, product
    return fallback, fallback


def _parse_plan_blob(blob: dict[str, object], user_query: str) -> dict[str, SiteSearchPlan]:
    by_norm = {_normalize_key(str(k)): v for k, v in blob.items()}
    out: dict[str, SiteSearchPlan] = {}
    for site, aliases in _SITE_JSON_KEYS.items():
        entry: object | None = None
        for alias in aliases:
            entry = by_norm.get(_normalize_key(alias))
            if entry is not None:
                break
        search_q, product_name = _parse_site_entry(entry, user_query)
        out[site] = SiteSearchPlan(
            user_query=user_query,
            search_query=search_q,
            match_query=product_name,
        )
    return out


def llm_site_search_plans(user_query: str) -> dict[str, SiteSearchPlan] | None:
    """One GPT call → per-site search_query + product_name. None if unavailable or failed."""
    user_query = user_query.strip()
    if not user_query:
        return None
    if not SETTINGS.openai_api_key:
        logger.warning("LLM site search plan skipped: OPENAI_API_KEY not set")
        return None

    user_prompt = (
        f"User query: {user_query}\n\n"
        "For Amazon, Best Buy, Walmart, and Newegg, return search_query and product_name for each."
    )

    try:
        from openai import OpenAI

        client = OpenAI(api_key=SETTINGS.openai_api_key)
        response = client.chat.completions.create(
            model=SETTINGS.openai_model,
            messages=[
                {"role": "system", "content": _PLAN_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        logger.warning("LLM site search plan failed: %s", e)
        return None

    if not isinstance(data, dict):
        return None

    plans = _parse_plan_blob(data, user_query)
    for site, plan in plans.items():
        short = site.split(".")[0]
        logger.info(
            "LLM search plan (%s) %s: search=%r product=%r",
            SETTINGS.openai_model,
            short,
            plan.search_query,
            plan.match_query,
        )
    return plans


def resolve_site_search_plans(user_query: str) -> dict[str, SiteSearchPlan]:
    """Plans for every adapter display_name; passthrough per site when LLM is off or fails."""
    user_query = user_query.strip()
    fallback = SiteSearchPlan.passthrough(user_query)
    plans = llm_site_search_plans(user_query)
    if not plans:
        return {site: fallback for site in _SITE_JSON_KEYS}
    return {site: plans.get(site, fallback) for site in _SITE_JSON_KEYS}
