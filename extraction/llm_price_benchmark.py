"""LLM reference prices for price-gap rescrape (compare scrape vs GPT estimate)."""

from __future__ import annotations

import json
import logging
from decimal import Decimal

from config import SETTINGS
from utils.parsing import parse_price

logger = logging.getLogger(__name__)

# ProductRow.website → JSON keys we accept from the model (normalized to lowercase alnum).
_SITE_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "Amazon.com": ("amazon",),
    "BestBuy.com": ("bestbuy", "best_buy", "best buy"),
    "Walmart.com": ("walmart",),
    "Newegg.com": ("newegg", "new_egg"),
}

_BENCHMARK_SYSTEM = """You answer questions about current US retail prices for consumer electronics.
Return ONLY valid JSON with these keys (USD numbers or null): amazon, bestbuy, walmart, newegg.
Use numeric values only (no currency symbols). Use null when you are not confident."""


def _normalize_key(key: str) -> str:
    return "".join(ch for ch in key.lower() if ch.isalnum())


def _coerce_price(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value <= 0:
            return None
        return Decimal(str(value))
    return parse_price(str(value))


def _extract_price_blob(data: object) -> dict[str, object]:
    if not isinstance(data, dict):
        return {}
    if all(k in data for k in ("amazon", "bestbuy", "walmart", "newegg")):
        return data
    for wrapper in ("prices", "retailers", "results", "data"):
        inner = data.get(wrapper)
        if isinstance(inner, dict):
            return inner
    return data


def _map_blob_to_sites(blob: dict[str, object]) -> dict[str, Decimal | None]:
    by_norm = {_normalize_key(str(k)): v for k, v in blob.items()}
    out: dict[str, Decimal | None] = {}
    for site, aliases in _SITE_KEY_ALIASES.items():
        price: Decimal | None = None
        for alias in aliases:
            raw = by_norm.get(_normalize_key(alias))
            if raw is not None:
                price = _coerce_price(raw)
                break
        out[site] = price
    return out


def llm_reference_prices_for_query(query: str) -> dict[str, Decimal | None] | None:
    """Ask the configured OpenAI model for per-retailer reference prices.

    User prompt format: "What the price in Amazon, Bestbuy, Walmart, Newegg for {query}"
    Returns None if the API call fails; otherwise a map keyed by ProductRow.website.
    """
    if not SETTINGS.openai_api_key:
        logger.warning("price-gap LLM benchmark skipped: OPENAI_API_KEY not set")
        return None

    user_prompt = f"What the price in Amazon, Bestbuy, Walmart, Newegg for {query}"

    try:
        from openai import OpenAI

        client = OpenAI(api_key=SETTINGS.openai_api_key)
        response = client.chat.completions.create(
            model=SETTINGS.openai_model,
            messages=[
                {"role": "system", "content": _BENCHMARK_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        logger.warning("price-gap LLM benchmark failed: %s", e)
        return None

    prices = _map_blob_to_sites(_extract_price_blob(data))
    logger.info(
        "LLM price benchmark (%s): %s",
        SETTINGS.openai_model,
        ", ".join(
            f"{site.split('.')[0]}=${prices[site]:,.2f}" if prices.get(site) else f"{site.split('.')[0]}=?"
            for site in _SITE_KEY_ALIASES
        ),
    )
    return prices


def relative_price_gap(found: Decimal, reference: Decimal) -> float:
    """Absolute relative difference |found - reference| / reference."""
    if reference <= 0:
        return 0.0
    return abs(float(found - reference)) / float(reference)
