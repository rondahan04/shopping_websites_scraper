"""Shared HTML / JSON parsing helpers."""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


def parse_price(text: str | None) -> Decimal | None:
    if not text:
        return None
    cleaned = re.sub(r"[^\d.,]", "", text.replace(",", ""))
    if not cleaned:
        return None
    # Handle 1.234,56 vs 1,234.56
    if cleaned.count(".") > 1 and "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned and "." not in cleaned:
        cleaned = cleaned.replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    try:
        value = Decimal(cleaned)
        return value if value > 0 else None
    except InvalidOperation:
        return None


def parse_rating(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", text.replace(",", "."))
    if not m:
        return None
    val = float(m.group(1))
    if val > 5 and val <= 50:
        val = val / 10.0
    if 0 <= val <= 5:
        return val
    return None


def parse_review_count(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"([\d,]+)\s*(?:rating|review|customer)?", text.lower())
    if not m:
        m = re.search(r"([\d,]+)", text)
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None


def extract_json_ld_products(soup: BeautifulSoup) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("@type") == "Product":
                products.append(item)
            elif "@graph" in item:
                for node in item["@graph"]:
                    if isinstance(node, dict) and node.get("@type") == "Product":
                        products.append(node)
    return products


def fields_from_json_ld(product: dict[str, Any]) -> tuple[str, Decimal | None, float | None, int | None]:
    title = product.get("name") or ""
    price = None
    rating = None
    reviews = None

    agg = product.get("aggregateRating") or {}
    if isinstance(agg, dict):
        rating = parse_rating(str(agg.get("ratingValue", "")))
        rc = agg.get("reviewCount") or agg.get("ratingCount")
        if rc is not None:
            try:
                reviews = int(str(rc).replace(",", ""))
            except ValueError:
                reviews = parse_review_count(str(rc))

    offers = product.get("offers")
    offer_list = offers if isinstance(offers, list) else [offers] if offers else []
    for offer in offer_list:
        if not isinstance(offer, dict):
            continue
        p = offer.get("price") or offer.get("lowPrice")
        if p is not None:
            price = parse_price(str(p))
            if price:
                break

    return title, price, rating, reviews


def visible_text(soup: BeautifulSoup, max_chars: int | None = None) -> str:
    if max_chars is None:
        from config import SETTINGS

        max_chars = SETTINGS.llm_max_chars
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    return text[:max_chars]


def absolute_url(base: str, href: str) -> str:
    return urljoin(base, href)


def is_same_domain(url: str, domain: str) -> bool:
    host = urlparse(url).netloc.lower()
    return domain.lower() in host
