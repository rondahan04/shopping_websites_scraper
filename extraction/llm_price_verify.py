"""GPT check: scraped PDP price vs expected US retail for the product."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal

from config import SETTINGS
from extraction import llm_health
from utils.parsing import parse_price

logger = logging.getLogger(__name__)

_VERIFY_SYSTEM = """You judge whether a scraped USD amount from an e-commerce product page is the main cash buy-box price for the product described.

Scrapers often mis-read:
- monthly payments or financing teasers (e.g. $89/mo shown as $89)
- add-on accessories or protection plans
- a secondary used/open-box offer when the listing is for a premium new item
- wrong currency or geo pricing mislabeled as dollars
- unrelated low offer lines when the real price is much higher

Return ONLY valid JSON:
{
  "plausible": true or false,
  "reason": "one short sentence",
  "expected_price_usd": number or null
}

plausible=true when the scraped price is a believable US retail cash price for this exact product (new, or clearly labeled refurb/open-box matching the title).

plausible=false when the scraped price is almost certainly not the real buy-box price for this product.

expected_price_usd: your best estimate of typical US retail for this product (single unit, main SKU), or null if unsure."""


@dataclass(frozen=True)
class PriceVerifyResult:
    plausible: bool
    reason: str
    expected_price_usd: Decimal | None = None
    # False means ``plausible`` is a fail-open default rather than a verdict —
    # the check was disabled, unconfigured, or the call failed. See the same
    # field on TitleVerifyResult.
    verified: bool = True


def _coerce_expected(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value <= 0:
            return None
        return Decimal(str(value))
    return parse_price(str(value))


def llm_verify_scraped_price(
    *,
    user_query: str,
    product_title: str,
    scraped_price: Decimal,
    retailer: str,
    source_url: str | None = None,
) -> PriceVerifyResult:
    """Ask the LLM whether ``scraped_price`` is a plausible US buy-box price for this PDP."""
    if not SETTINGS.llm_price_verify_enabled:
        # Same reasoning as the title verifier: off by choice is still off.
        llm_health.record_unavailable(llm_health.PRICE_VERIFY, "disabled by configuration")
        return PriceVerifyResult(True, "price verify disabled", verified=False)
    if not SETTINGS.openai_api_key:
        llm_health.record_unavailable(llm_health.PRICE_VERIFY, "OPENAI_API_KEY not set")
        return PriceVerifyResult(True, "no api key", verified=False)
    # A non-positive price is a real determination, not a fail-open default.
    if scraped_price <= 0:
        return PriceVerifyResult(False, "non-positive scraped price")

    title = product_title.strip()
    if not title:
        return PriceVerifyResult(True, "empty title", verified=False)

    user_prompt = (
        f"Retailer: {retailer}\n"
        f"User search query: {user_query}\n"
        f"Product page title: {product_title}\n"
        f"Scraped price (USD): {scraped_price:,.2f}\n"
    )
    if source_url:
        user_prompt += f"Product URL: {source_url}\n"
    user_prompt += (
        "\nIs this scraped USD amount the plausible main cash buy-box price for this product?"
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
        logger.warning("LLM price verify failed (allowing price unchecked): %s", e)
        llm_health.record_unavailable(llm_health.PRICE_VERIFY, str(e))
        return PriceVerifyResult(True, f"verify error: {e}", verified=False)

    plausible = data.get("plausible")
    if isinstance(plausible, str):
        plausible = plausible.strip().lower() in ("true", "yes", "1")
    else:
        plausible = bool(plausible)
    reason = str(data.get("reason") or "").strip() or (
        "plausible" if plausible else "implausible"
    )
    expected = _coerce_expected(data.get("expected_price_usd"))

    return PriceVerifyResult(plausible, reason, expected)
