"""
Review Bombing & Fake Review Detector.

Uses OpenAI (gpt-4o-mini) to analyze a product's review corpus for trust signals:
  - Sudden rating spikes (review bombing patterns)
  - Generic / non-specific praise language
  - Repetitive phrasing that suggests bot networks
  - Incentivized-review disclosures
  - 1-star bombing unrelated to product quality (e.g., shipping complaints)

Design choices:
  - We sample rather than send every review to keep token costs low while
    preserving statistical signal.  20 from each polar extreme gives the LLM
    enough diversity without blowing the context window.
  - We do a pre-pass in Python (rating spike detection) so the LLM can focus
    on linguistic analysis — tasks it is actually good at.
  - response_format=json_object forces valid JSON back so we never need to
    retry due to malformed output.
"""

from __future__ import annotations

import json
import os
import random
from collections import Counter, defaultdict
from datetime import date
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Data schemas
# ---------------------------------------------------------------------------


class Review(BaseModel):
    """A single user review as scraped from a product page."""

    review_id: str
    rating: int = Field(..., ge=1, le=5, description="Star rating 1-5")
    title: str
    text: str
    date: date


class TrustAnalysisOutput(BaseModel):
    """Structured result returned by the LLM trust analysis."""

    trust_score_1_to_10: int = Field(
        ...,
        ge=1,
        le=10,
        description="1 = almost certainly manipulated, 10 = highly trustworthy",
    )
    warning_flags: list[str] = Field(
        default_factory=list,
        description="Human-readable warning strings, e.g. 'Spike of 47 five-star reviews on 2024-03-01'",
    )
    summary: str = Field(
        ..., description="2-3 sentence plain-English summary of the analysis"
    )
    suspicious_review_ids: list[str] = Field(
        default_factory=list,
        description="IDs of individual reviews the LLM deemed suspicious",
    )


# ---------------------------------------------------------------------------
# Spike detection helpers (pure Python — no LLM tokens spent here)
# ---------------------------------------------------------------------------

_SPIKE_THRESHOLD = 0.4  # A single day accounting for >40% of same-rating reviews
# is a strong signal of coordinated activity.


def _detect_rating_spikes(reviews: list[Review]) -> list[str]:
    """
    Group reviews by (rating, date) and flag dates where a rating's daily count
    exceeds SPIKE_THRESHOLD of that rating's total count.

    Returns a list of warning strings ready to inject into the LLM prompt.
    """
    # Build: rating -> {date -> [review_ids]}
    by_rating_date: dict[int, dict[date, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for r in reviews:
        by_rating_date[r.rating][r.date].append(r.review_id)

    warnings: list[str] = []
    for rating, date_map in by_rating_date.items():
        total = sum(len(ids) for ids in date_map.values())
        if total < 5:
            # Too few reviews to be statistically meaningful
            continue
        for day, ids in date_map.items():
            fraction = len(ids) / total
            if fraction >= _SPIKE_THRESHOLD:
                warnings.append(
                    f"Spike detected: {len(ids)} out of {total} total {rating}-star "
                    f"reviews arrived on {day} ({fraction:.0%} of that rating's total). "
                    f"Affected IDs: {', '.join(ids[:5])}{'…' if len(ids) > 5 else ''}"
                )
    return warnings


def _rating_distribution(reviews: list[Review]) -> dict[int, int]:
    """Return {star_rating: count} for the full corpus."""
    return dict(Counter(r.rating for r in reviews))


# ---------------------------------------------------------------------------
# Main analyzer class
# ---------------------------------------------------------------------------

_SAMPLE_SIZE = 20  # Reviews sampled per polar rating to cap token usage


class ReviewTrustAnalyzer:
    """
    Analyzes a product's review corpus for signs of manipulation.

    Args:
        reviews: Full list of scraped Review objects for one product.
        openai_api_key: Falls back to the OPENAI_API_KEY environment variable.
        model: OpenAI chat model.  gpt-4o-mini offers the best cost/quality
               ratio for text classification tasks like this.
               gpt-5.4-mini is the latest cost-optimised model in the 4.5 family.
    """

    def __init__(
        self,
        reviews: list[Review],
        openai_api_key: str | None = None,
        model: str = "gpt-5.4-mini",
    ) -> None:
        self.reviews = reviews
        self.model = model
        self._client = OpenAI(api_key=openai_api_key or os.environ["OPENAI_API_KEY"])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_reviews(self) -> TrustAnalysisOutput:
        """
        Run the full trust analysis pipeline:
          1. Pre-compute rating distribution and spike warnings in Python.
          2. Sample polar-extreme reviews (5-star + 1-star) for LLM analysis.
          3. Send a structured prompt to gpt-4o-mini requesting JSON output.
          4. Parse and return a TrustAnalysisOutput.
        """
        if not self.reviews:
            return TrustAnalysisOutput(
                trust_score_1_to_10=5,
                warning_flags=["No reviews available for analysis."],
                summary="No reviews were provided; no analysis performed.",
                suspicious_review_ids=[],
            )

        # Step 1: Python-side statistical pre-analysis (zero API cost)
        distribution = _rating_distribution(self.reviews)
        spike_warnings = _detect_rating_spikes(self.reviews)

        # Step 2: Sample to control token cost.
        # We focus on the extremes (1-star and 5-star) because:
        #  - 5-star: most common target for fake/incentivized reviews
        #  - 1-star: most common target for review bombing campaigns
        five_stars = [r for r in self.reviews if r.rating == 5]
        one_stars = [r for r in self.reviews if r.rating == 1]
        sample_5 = random.sample(five_stars, min(_SAMPLE_SIZE, len(five_stars)))
        sample_1 = random.sample(one_stars, min(_SAMPLE_SIZE, len(one_stars)))
        sampled = sample_5 + sample_1

        # Step 3: Build prompt
        system_prompt = self._build_system_prompt(distribution, spike_warnings)
        user_payload = self._format_reviews_for_prompt(sampled)

        # Step 4: Call the LLM with JSON mode enforced
        response = self._client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_payload},
            ],
            temperature=0.1,  # Low temperature for consistent classification
        )

        raw_json: dict[str, Any] = json.loads(
            response.choices[0].message.content or "{}"
        )

        # Merge Python-detected spike warnings into LLM output so nothing is lost
        llm_flags: list[str] = raw_json.get("warning_flags", [])
        merged_flags = spike_warnings + [f for f in llm_flags if f not in spike_warnings]
        raw_json["warning_flags"] = merged_flags

        return TrustAnalysisOutput(**raw_json)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_system_prompt(
        self, distribution: dict[int, int], spike_warnings: list[str]
    ) -> str:
        dist_str = ", ".join(
            f"{stars}★: {count}" for stars, count in sorted(distribution.items())
        )
        spike_block = (
            "\n".join(f"  - {w}" for w in spike_warnings)
            if spike_warnings
            else "  None detected by statistical pre-analysis."
        )
        return f"""You are an expert e-commerce review quality analyst specializing in \
detecting fake, incentivized, and coordinated reviews.

## Context you have been given
Rating distribution for this product: {dist_str}
Statistical spike warnings (pre-computed):
{spike_block}

## Your task
Analyze the sampled reviews below and return a JSON object matching this exact schema:

{{
  "trust_score_1_to_10": <integer 1-10>,
  "warning_flags": [<list of specific warning strings>],
  "summary": "<2-3 sentence plain-English verdict>",
  "suspicious_review_ids": [<list of review_id strings>]
}}

## Detection criteria — flag each that applies
1. GENERIC PRAISE — Reviews that say nothing product-specific.  \
   ("Great product!", "Fast shipping!", "Love it!" with no details)
2. REPETITIVE PHRASING — Multiple reviews that share unusual phrases verbatim or \
   near-verbatim, suggesting copy-paste bots.
3. REVIEW BOMBING — A cluster of 1-star reviews where the complaint is clearly \
   unrelated to product quality (shipping delays, wrong seller, country of origin).
4. INCENTIVIZED LANGUAGE — Explicit or coded disclosure: \
   "received free", "in exchange for", "gifted", "sponsored", "#ad", \
   "complimentary", "discount code".
5. TEMPORAL ANOMALY — Reference the pre-computed spike warnings above if relevant.
6. SUSPICIOUSLY SHORT OR LONG — All 5-star reviews under 10 words, or \
   identically structured long reviews that feel templated.

## Scoring guide
10: Overwhelmingly authentic, specific, varied.
7-9: Mostly authentic with minor concerns.
4-6: Noticeable manipulation signals; buyer should be cautious.
1-3: Strong evidence of coordinated fake activity.

Return ONLY the JSON object — no markdown, no prose outside the JSON."""

    @staticmethod
    def _format_reviews_for_prompt(reviews: list[Review]) -> str:
        """Serialize sampled reviews into a compact, token-efficient format."""
        lines = [
            f"[{r.review_id}] {r.rating}★ | {r.date} | {r.title!r} | {r.text[:300]}"
            for r in reviews
        ]
        return (
            f"Below are {len(reviews)} sampled reviews "
            f"(up to 20 five-star and 20 one-star):\n\n"
            + "\n".join(lines)
        )


# ---------------------------------------------------------------------------
# Dummy data + smoke test
# ---------------------------------------------------------------------------


def _make_dummy_reviews() -> list[Review]:
    """
    Construct a realistic but synthetic corpus that exercises every detector:
      - A spike of generic 5-star reviews on one day (bot wave)
      - Incentivized language in some reviews
      - Review bombing with shipping complaints on 1-star
      - A handful of genuine, specific reviews to give contrast
    """
    def d(offset_days: int) -> date:
        return date(2024, 1, 1 + offset_days)

    reviews: list[Review] = []

    # ---- Genuine reviews scattered over time ----
    genuine_data = [
        (1, 4, "Solid build quality", "The aluminum chassis feels premium and the keyboard travel is exactly what I wanted for long typing sessions.", d(0)),
        (2, 5, "Best laptop I've owned", "Battery easily lasts 10 hours in mixed use. Screen calibration is excellent for photo editing.", d(2)),
        (3, 3, "Good but runs warm", "Performance is great but under sustained load the fans get loud and the bottom plate gets uncomfortably hot.", d(5)),
        (4, 4, "Almost perfect", "The trackpad is smooth and gestures work flawlessly. Only wish it had an SD card slot.", d(7)),
        (5, 2, "Dead pixels out of the box", "Received the unit with three dead pixels in the lower-right corner. Had to return it.", d(10)),
    ]
    for rid, rating, title, text, day in genuine_data:
        reviews.append(Review(review_id=f"R{rid:03d}", rating=rating, title=title, text=text, date=day))

    # ---- Bot wave: 12 generic 5-star reviews posted on the same day ----
    generic_5star = [
        "Great product! Fast shipping!",
        "Excellent! Would buy again.",
        "Amazing product, very happy.",
        "Perfect. Arrived quickly.",
        "Great value for the money!",
        "Highly recommend. Great product!",
        "Five stars, no issues.",
        "Very satisfied with purchase.",
        "Good product, fast delivery.",
        "Great, exactly as described!",
        "Wonderful product!",
        "Love it! Great buy.",
    ]
    for i, text in enumerate(generic_5star, start=10):
        reviews.append(Review(
            review_id=f"R{i:03d}",
            rating=5,
            title="Great product!",
            text=text,
            date=d(14),  # All on the same day — spike
        ))

    # ---- Incentivized reviews ----
    reviews.append(Review(
        review_id="R030",
        rating=5,
        title="Received free for review",
        text="I received this product for free in exchange for my honest review. It works as advertised.",
        date=d(16),
    ))
    reviews.append(Review(
        review_id="R031",
        rating=5,
        title="Gifted unit - honest thoughts",
        text="This was gifted to me by the brand ambassador. Complimentary unit, my opinions are my own. Great laptop!",
        date=d(17),
    ))

    # ---- Review bombing: 1-star complaints about shipping/seller, not product ----
    bombing_texts = [
        "Seller sent the wrong color. Horrible customer service. 1 star.",
        "Package arrived crushed. Obviously a shipping problem but ruined my Christmas gift.",
        "This took 45 days to arrive from China. Never again. Product itself is fine.",
        "Wrong item sent. Seller won't respond. Amazon dispute opened.",
        "Do NOT buy from this third-party seller. The product is fake.",
    ]
    for i, text in enumerate(bombing_texts, start=40):
        reviews.append(Review(
            review_id=f"R{i:03d}",
            rating=1,
            title="Terrible experience",
            text=text,
            date=d(20),  # All on same day
        ))

    return reviews


if __name__ == "__main__":
    print("=" * 60)
    print("Review Trust Analyzer — Demo")
    print("=" * 60)

    dummy_reviews = _make_dummy_reviews()
    print(f"Loaded {len(dummy_reviews)} dummy reviews.\n")

    analyzer = ReviewTrustAnalyzer(reviews=dummy_reviews)
    result = analyzer.analyze_reviews()

    print(f"Trust Score : {result.trust_score_1_to_10}/10")
    print(f"\nWarning Flags ({len(result.warning_flags)}):")
    for flag in result.warning_flags:
        print(f"  ⚠  {flag}")
    print(f"\nSummary:\n  {result.summary}")
    print(f"\nSuspicious Review IDs: {result.suspicious_review_ids}")
