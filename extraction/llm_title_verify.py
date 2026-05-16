"""GPT check: scraped SERP listing title vs LLM expected product name."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Literal

from config import SETTINGS

logger = logging.getLogger(__name__)

TitleVerifyAction = Literal[
    "accept",
    "try_next_candidate",
    "refine_search",
    "reject_junk",
]

_VERIFY_SYSTEM = """You judge whether two e-commerce product titles refer to the same product SKU.
The user searched for a product. An earlier step produced the expected product name for this retailer.
A scraper found a listing title on the search results page.

Rules for match=true:
- Same core product SKU (allow color, storage/capacity, "2nd Gen" vs no generation label, minor wording).
- Prefer NEW retail when the user did not ask for used/renewed/refurbished/open-box.
- match=true for renewed/refurb/open-box only when the user query mentions those conditions OR the listing title clearly states that condition and it is still the same product family.

Rules for match=false — pick exactly one action:
- try_next_candidate: listing is renewed/refurbished/open-box/used but the user wants standard new retail (most headphone/laptop searches).
- try_next_candidate: wrong product but SERP ranking may have other rows (different brand, earbuds vs over-ear headphones, accessory).
- refine_search: listing is junk/ambiguous (e.g. "See options", price-only text) OR search terms should change (e.g. add "over-ear", model number, exclude "earbuds").
- reject_junk: not a product title at all.

Return ONLY valid JSON:
{
  "match": true or false,
  "reason": "one short sentence",
  "action": "accept" | "try_next_candidate" | "refine_search" | "reject_junk",
  "suggested_search": "optional shorter search string for this retailer, or null"
}

When match=true, set action to "accept" and suggested_search to null."""


@dataclass(frozen=True)
class TitleVerifyResult:
    match: bool
    reason: str
    action: TitleVerifyAction
    suggested_search: str | None = None


def _parse_action(raw: object, *, match: bool) -> TitleVerifyAction:
    if match:
        return "accept"
    action = str(raw or "try_next_candidate").strip().lower().replace("-", "_")
    if action in ("try_next_candidate", "refine_search", "reject_junk"):
        return action  # type: ignore[return-value]
    return "try_next_candidate"


def llm_verify_listing_title(
    *,
    user_query: str,
    expected_product_name: str,
    scraped_listing_title: str,
    retailer: str,
) -> TitleVerifyResult:
    """Compare scraped SERP title to expected product name; suggest next step when they differ."""
    if not SETTINGS.llm_title_verify_enabled:
        return TitleVerifyResult(True, "title verify disabled", "accept")
    if not SETTINGS.openai_api_key:
        return TitleVerifyResult(True, "no api key", "accept")
    expected = expected_product_name.strip()
    scraped = scraped_listing_title.strip()
    if not expected or not scraped:
        return TitleVerifyResult(True, "empty title", "accept")
    if expected.lower() == scraped.lower():
        return TitleVerifyResult(True, "exact title match", "accept")

    user_prompt = (
        f"Retailer: {retailer}\n"
        f"User search query: {user_query}\n"
        f"Expected product name: {expected_product_name}\n"
        f"Scraped listing title: {scraped_listing_title}\n\n"
        "Do these refer to the same product? If not, what should the scraper do next?"
    )

    try:
        from openai import OpenAI

        client = OpenAI(api_key=SETTINGS.openai_api_key)
        response = client.chat.completions.create(
            model=SETTINGS.openai_model,
            messages=[
                {"role": "system", "content": _VERIFY_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        logger.warning("LLM title verify failed (allowing listing): %s", e)
        return TitleVerifyResult(True, f"verify error: {e}", "accept")

    match = data.get("match")
    if isinstance(match, str):
        match = match.strip().lower() in ("true", "yes", "1")
    else:
        match = bool(match)
    reason = str(data.get("reason") or "").strip() or ("match" if match else "mismatch")
    action = _parse_action(data.get("action"), match=match)
    suggested = data.get("suggested_search")
    suggested_search = str(suggested).strip() if suggested else None
    if action == "refine_search" and not suggested_search:
        suggested_search = expected_product_name

    return TitleVerifyResult(match, reason, action, suggested_search)
