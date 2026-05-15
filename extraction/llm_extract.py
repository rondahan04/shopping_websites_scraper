"""Method 3: LLM structured extraction from page text."""

from __future__ import annotations

import json

from bs4 import BeautifulSoup

from config import SETTINGS
from models import ExtractionFailure, ExtractionMethod, ProductFields, SearchResult
from sites.base import SiteAdapter
from utils.parsing import parse_price, parse_rating, parse_review_count, visible_text
from validation.fields import validate_product_fields

SCHEMA_PROMPT = """Extract product data from this e-commerce page text.
Return ONLY valid JSON with keys: title (string), price (number or null), average_rating (number 0-5 or null), review_count (integer or null).
Use null for missing fields. Price should be numeric USD without currency symbol."""

SERP_PROMPT = """Extract organic product search results from this e-commerce search results page.
Return ONLY valid JSON: {"results": [{"title": "...", "url": "..."}, ...]}
Include up to 10 organic product listings (skip ads/sponsored). URLs must be absolute https URLs."""


def extract_with_llm(html: str, url: str) -> ProductFields:
    if not SETTINGS.openai_api_key:
        raise ExtractionFailure("OPENAI_API_KEY not set", ExtractionMethod.LLM)

    soup = BeautifulSoup(html, "lxml")
    text = visible_text(soup)

    try:
        from openai import OpenAI

        client = OpenAI(api_key=SETTINGS.openai_api_key)
        response = client.chat.completions.create(
            model=SETTINGS.openai_model,
            messages=[
                {"role": "system", "content": SCHEMA_PROMPT},
                {
                    "role": "user",
                    "content": f"URL: {url}\n\nPage text:\n{text}",
                },
            ],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        raise ExtractionFailure(f"llm extraction failed: {e}", ExtractionMethod.LLM) from e

    title = str(data.get("title") or "").strip()
    price_raw = data.get("price")
    price = None
    if price_raw is not None:
        price = parse_price(str(price_raw))

    rating_raw = data.get("average_rating")
    rating = None
    if rating_raw is not None:
        try:
            rating = float(rating_raw)
        except (TypeError, ValueError):
            rating = parse_rating(str(rating_raw))

    reviews_raw = data.get("review_count")
    reviews = None
    if reviews_raw is not None:
        try:
            reviews = int(reviews_raw)
        except (TypeError, ValueError):
            reviews = parse_review_count(str(reviews_raw))

    fields = ProductFields(
        title=title,
        price=price,
        average_rating=rating,
        review_count=reviews,
    )
    validate_product_fields(fields)
    return fields


def parse_serp_with_llm(html: str, search_url: str, adapter: SiteAdapter) -> list[SearchResult]:
    if not SETTINGS.openai_api_key:
        raise ExtractionFailure("OPENAI_API_KEY not set", ExtractionMethod.LLM)

    soup = BeautifulSoup(html, "lxml")
    text = visible_text(soup)

    try:
        from openai import OpenAI

        client = OpenAI(api_key=SETTINGS.openai_api_key)
        response = client.chat.completions.create(
            model=SETTINGS.openai_model,
            messages=[
                {"role": "system", "content": SERP_PROMPT},
                {
                    "role": "user",
                    "content": f"Store: {adapter.display_name}\nSearch URL: {search_url}\n\nPage text:\n{text}",
                },
            ],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        raise ExtractionFailure(f"llm serp parse failed: {e}", ExtractionMethod.LLM) from e

    results: list[SearchResult] = []
    for idx, item in enumerate(data.get("results") or [], start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if not title or not url.startswith("http"):
            continue
        if not adapter.is_product_url(url):
            continue
        results.append(SearchResult(title=title, url=url.split("?")[0], rank=idx))
        if idx >= SETTINGS.max_serp_results:
            break
    if not results:
        raise ExtractionFailure("llm returned no valid serp results", ExtractionMethod.LLM)
    return results
