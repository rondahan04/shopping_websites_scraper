"""Method 4: Firecrawl API extraction."""

from __future__ import annotations

import json

import httpx

from config import SETTINGS
from models import ExtractionFailure, ExtractionMethod, ProductFields
from utils.parsing import parse_price, parse_rating, parse_review_count
from validation.fields import validate_product_fields

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "price": {"type": "number"},
        "average_rating": {"type": "number"},
        "review_count": {"type": "integer"},
    },
}


def extract_with_firecrawl(url: str) -> ProductFields:
    if not SETTINGS.firecrawl_api_key:
        raise ExtractionFailure("FIRECRAWL_API_KEY not set", ExtractionMethod.FIRECRAWL)

    headers = {
        "Authorization": f"Bearer {SETTINGS.firecrawl_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "url": url,
        "formats": ["extract"],
        "extract": {
            "schema": SCHEMA,
            "prompt": "Extract the main product title, current price in USD, average star rating, and review count.",
        },
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(SETTINGS.firecrawl_api_url, headers=headers, json=payload)
        if resp.status_code in (403, 429):
            raise ExtractionFailure(f"firecrawl http {resp.status_code}", ExtractionMethod.FIRECRAWL)
        resp.raise_for_status()
        body = resp.json()
    except ExtractionFailure:
        raise
    except Exception as e:
        raise ExtractionFailure(f"firecrawl request failed: {e}", ExtractionMethod.FIRECRAWL) from e

    data = body.get("data") or {}
    extracted = data.get("extract") or data.get("json") or {}
    if isinstance(extracted, str):
        extracted = json.loads(extracted)

    title = str(extracted.get("title") or "").strip()
    price = parse_price(str(extracted.get("price", ""))) if extracted.get("price") is not None else None
    rating = None
    if extracted.get("average_rating") is not None:
        try:
            rating = float(extracted["average_rating"])
        except (TypeError, ValueError):
            rating = parse_rating(str(extracted["average_rating"]))
    reviews = None
    if extracted.get("review_count") is not None:
        try:
            reviews = int(extracted["review_count"])
        except (TypeError, ValueError):
            reviews = parse_review_count(str(extracted["review_count"]))

    fields = ProductFields(
        title=title,
        price=price,
        average_rating=rating,
        review_count=reviews,
    )
    validate_product_fields(fields)
    return fields


def fetch_html_firecrawl(url: str, *, wait_ms: int | None = None) -> str:
    """Fetch raw HTML/markdown for a URL via Firecrawl (search or product pages)."""
    if not SETTINGS.firecrawl_api_key:
        raise ExtractionFailure("FIRECRAWL_API_KEY not set", ExtractionMethod.FIRECRAWL)

    headers = {
        "Authorization": f"Bearer {SETTINGS.firecrawl_api_key}",
        "Content-Type": "application/json",
    }
    payload: dict = {"url": url, "formats": ["html"]}
    if wait_ms is not None:
        payload["waitFor"] = wait_ms
    elif "bestbuy.com" in url.lower():
        # Best Buy SERP is a JS shell; allow the product grid to hydrate.
        payload["waitFor"] = 8000

    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(SETTINGS.firecrawl_api_url, headers=headers, json=payload)
        if resp.status_code in (403, 429):
            raise ExtractionFailure(f"firecrawl http {resp.status_code}", ExtractionMethod.FIRECRAWL)
        resp.raise_for_status()
        body = resp.json()
    except ExtractionFailure:
        raise
    except Exception as e:
        raise ExtractionFailure(f"firecrawl fetch failed: {e}", ExtractionMethod.FIRECRAWL) from e

    data = body.get("data") or {}
    html = data.get("html") or data.get("rawHtml") or ""
    if not html:
        raise ExtractionFailure("firecrawl returned empty html", ExtractionMethod.FIRECRAWL)
    return html
