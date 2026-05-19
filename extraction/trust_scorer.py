"""AI-powered review trust scoring for scraped product rows."""

from __future__ import annotations

import json
import logging

from config import SETTINGS
from models import ProductRow

logger = logging.getLogger(__name__)

_TRUST_SYSTEM = """You assess whether a product's review rating on an e-commerce site looks trustworthy.

Common signs of manipulated reviews:
- Near-perfect average rating (4.8+) on a commodity product with tens of thousands of reviews
- Very high review count on a product that has only been on the market a short time
- Suspiciously uniform high ratings without the normal distribution of lower scores

Return ONLY valid JSON:
{
  "trust_label": "Low" | "Medium" | "High",
  "trust_reason": "one short sentence"
}

trust_label:
  High   = rating pattern looks authentic
  Medium = nothing suspicious but limited signal to judge
  Low    = rating pattern shows signs of manipulation or is suspiciously perfect

trust_reason: one sentence explaining your assessment (max 15 words)."""


def _parse_rating(s: str) -> float | None:
    if s == "N/A":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_review_count(s: str) -> int | None:
    if s == "N/A":
        return None
    try:
        return int(s.replace(",", ""))
    except ValueError:
        return None


def _heuristic(avg_rating: str, review_count: str) -> tuple[str, str]:
    rating = _parse_rating(avg_rating)
    count = _parse_review_count(review_count)

    if rating is None or count is None:
        return "Unknown", ""

    if rating >= 4.8 and count >= 10_000:
        return "Low", "Suspiciously perfect rating on a high-volume product."

    return "Medium", "Rating pattern looks normal."


def score_trust_inplace(row: ProductRow) -> None:
    """Score review trust for one row and mutate trust_label / trust_reason in place."""
    if not SETTINGS.openai_api_key:
        label, reason = _heuristic(row.average_rating, row.review_count)
        row.trust_label = label
        row.trust_reason = reason
        return

    rating = _parse_rating(row.average_rating)
    count = _parse_review_count(row.review_count)

    if rating is None or count is None:
        row.trust_label = "Unknown"
        row.trust_reason = ""
        return

    user_prompt = (
        f"Retailer: {row.website}\n"
        f"Product: {row.product_title}\n"
        f"Average rating: {row.average_rating}\n"
        f"Review count: {row.review_count}\n"
        f"Price: {row.price}\n"
        "\nDoes this review pattern look trustworthy?"
    )

    try:
        from openai import OpenAI

        client = OpenAI(api_key=SETTINGS.openai_api_key)
        response = client.chat.completions.create(
            model=SETTINGS.openai_model,
            messages=[
                {"role": "system", "content": _TRUST_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        logger.warning("[%s] Trust scorer LLM call failed — using heuristic: %s", row.website, e)
        label, reason = _heuristic(row.average_rating, row.review_count)
        row.trust_label = label
        row.trust_reason = reason
        return

    label = str(data.get("trust_label") or "").strip()
    if label not in ("Low", "Medium", "High"):
        label, reason = _heuristic(row.average_rating, row.review_count)
        row.trust_label = label
        row.trust_reason = reason
        return

    row.trust_label = label
    row.trust_reason = str(data.get("trust_reason") or "").strip()
