"""Stage 4 — Firecrawl API (external scraping / extraction service)."""

from __future__ import annotations

import json
import logging
import time

import httpx

from config import SETTINGS
from utils.page_settle import firecrawl_wait_ms

logger = logging.getLogger(__name__)
from models import ExtractionFailure, ExtractionMethod, ProductFields
from utils.parsing import parse_price, parse_rating, parse_review_count
from validation.fields import validate_product_fields

def _firecrawl_post(payload: dict, *, retries: int = 2) -> dict:
    """POST to Firecrawl with one retry on transient 5xx."""
    headers = {
        "Authorization": f"Bearer {SETTINGS.firecrawl_api_key}",
        "Content-Type": "application/json",
    }
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(SETTINGS.firecrawl_api_url, headers=headers, json=payload)
            if resp.status_code in (403, 429):
                raise ExtractionFailure(
                    f"firecrawl http {resp.status_code}", ExtractionMethod.FIRECRAWL
                )
            if resp.status_code >= 500 and attempt < retries:
                logger.info("firecrawl %s, retry %d", resp.status_code, attempt + 1)
                time.sleep(1.5 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.json()
        except ExtractionFailure:
            raise
        except Exception as e:
            last_err = e
            if attempt < retries:
                logger.info("firecrawl request error, retry %d: %s", attempt + 1, e)
                time.sleep(1.5 * (attempt + 1))
                continue
            raise ExtractionFailure(
                f"firecrawl request failed: {e}", ExtractionMethod.FIRECRAWL
            ) from e
    raise ExtractionFailure(f"firecrawl request failed: {last_err}", ExtractionMethod.FIRECRAWL)


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

    payload = {
        "url": url,
        "formats": ["extract"],
        "extract": {
            "schema": SCHEMA,
            "prompt": "Extract the main product title, current price in USD, average star rating, and review count.",
        },
    }

    body = _firecrawl_post(payload)
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

    payload: dict = {"url": url, "formats": ["html"]}
    if wait_ms is not None:
        payload["waitFor"] = firecrawl_wait_ms(wait_ms)
    elif "bestbuy.com" in url.lower():
        # Best Buy SERP is a JS shell; allow the product grid to hydrate.
        payload["waitFor"] = firecrawl_wait_ms(8000)
    elif "walmart.com" in url.lower():
        payload["waitFor"] = firecrawl_wait_ms(7000)
    else:
        floor = firecrawl_wait_ms(None)
        if floor:
            payload["waitFor"] = floor

    body = _firecrawl_post(payload)
    data = body.get("data") or {}
    html = data.get("html") or data.get("rawHtml") or ""
    if not html:
        raise ExtractionFailure("firecrawl returned empty html", ExtractionMethod.FIRECRAWL)
    return html
