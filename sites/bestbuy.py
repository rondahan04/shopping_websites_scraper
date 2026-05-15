"""BestBuy.com adapter."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from config import SETTINGS
from models import ExtractionFailure, ProductFields, SearchResult
from sites.base import SiteAdapter
from utils.parsing import absolute_url, is_same_domain, parse_price, parse_rating, parse_review_count

# PDP: /site/<slug>/<sku>.p or /site/.../<6+digit sku> (LLM often drops “.p”); exclude SERP/compare.
_BB_NUMERIC_SKU = re.compile(r"/(\d{6,})(?:\.p)?(?:/|$|\?)", re.I)


def _bestbuy_looks_like_pdp(url: str) -> bool:
    if not is_same_domain(url, "bestbuy.com"):
        return False
    parsed = urlparse(url)
    path = parsed.path or ""
    lower_path = path.lower()
    if "/site/" not in path:
        return False
    if "searchpage.jsp" in lower_path or "/site/compare/" in lower_path:
        return False
    if ".p" in path:
        return True
    if "skuid=" in (parsed.query or "").lower():
        return bool(_BB_NUMERIC_SKU.search(path))
    return bool(_BB_NUMERIC_SKU.search(path))


def _title_from_bestbuy_canon_url(canon: str) -> str:
    parts = [p for p in urlparse(canon).path.split("/") if p and p.lower() != "site"]
    if not parts:
        return "Best Buy product"
    slug = parts[-2] if len(parts) >= 2 else parts[-1]
    slug = re.sub(r"\.p$", "", slug, flags=re.I)
    if slug.isdigit():
        return f"Best Buy SKU {slug}"
    return slug.replace("-", " ").title()[:160]


def salvage_bestbuy_serp_links(html: str, base_url: str) -> list[SearchResult]:
    """Recover PDP links embedded in JSON/scripts when the DOM layout does not match our selectors."""
    seen: set[str] = set()
    out: list[SearchResult] = []
    rank = 0
    patterns = (
        r"https://(?:www\.)?bestbuy\.com/site/[^\s\"'<>]+\d{6,}\.p(?:\?[^\s\"'<>]*)?",
        r"https://(?:www\.)?bestbuy\.com/site/[^\s\"'<>/]+/\d{6,}(?:\?[^\s\"'<>]*)?",
        r'["\'](/site/[^\s"\']+\d{6,}\.p)["\']',
        r'["\'](/site/[^\s"\']+/\d{6,})["\']',
    )
    for pat in patterns:
        for m in re.finditer(pat, html, re.I):
            raw = m.group(1) if m.lastindex else m.group(0)
            url = absolute_url(base_url, raw) if raw.startswith("/") else raw
            url = url.split('"')[0].split("#")[0].strip()
            if not _bestbuy_looks_like_pdp(url):
                continue
            canon = url.split("?")[0].rstrip("/")
            if canon in seen:
                continue
            seen.add(canon)
            rank += 1
            title = _title_from_bestbuy_canon_url(canon)
            out.append(SearchResult(title=title, url=canon, rank=rank))
            if rank >= SETTINGS.max_serp_results:
                return out
    return out


class BestBuyAdapter(SiteAdapter):
    display_name = "BestBuy.com"
    domain = "bestbuy.com"

    def build_search_url(self, query: str) -> str:
        return f"https://www.bestbuy.com/site/searchpage.jsp?st={self.encoded_query(query)}"

    def is_product_url(self, url: str) -> bool:
        return _bestbuy_looks_like_pdp(url)

    def parse_search_results(self, html: str, base_url: str) -> list[SearchResult]:
        soup = BeautifulSoup(html, "lxml")
        results: list[SearchResult] = []
        rank = 0

        selectors = (
            "li.sku-item",
            "div.sku-item",
            "[data-test-id='sku-item-wrapper']",
            "[data-testid='shop-product-card-wrapper']",
            ".sku-item-wrapper",
            "[data-test-id='sku-list-item-wrapper']",
        )

        containers: list[Any] = []
        seen_ctr: set[int] = set()
        for sel in selectors:
            for el in soup.select(sel):
                ctr_id = id(el)
                if ctr_id not in seen_ctr:
                    seen_ctr.add(ctr_id)
                    containers.append(el)

        link_selectors = (
            "h4.sku-title a",
            ".sku-title a",
            "a[data-testid='product-title']",
            "a[data-testid='product-overview-link']",
            "div.sku-title a",
            "h4[class*='sku-title'] a",
        )

        seen_urls: set[str] = set()
        for item in containers:
            if item.select_one(".sponsored, [data-testid*='sponsor']"):
                continue
            link = None
            for ls in link_selectors:
                link = item.select_one(ls)
                if link:
                    break
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if not title or not href:
                continue
            url = absolute_url(base_url, href)
            if not self.is_product_url(url):
                continue
            canon = url.split("?")[0]
            if canon in seen_urls:
                continue
            seen_urls.add(canon)
            rank += 1
            results.append(SearchResult(title=title, url=canon, rank=rank))
            if rank >= SETTINGS.max_serp_results:
                break

        if results:
            return results

        for a in soup.select('a[href*="/site/"]'):
            href = a.get("href", "")
            if "/site/" not in href:
                continue
            url = absolute_url(base_url, href)
            if not _bestbuy_looks_like_pdp(url):
                continue
            title = a.get_text(strip=True)
            if len(title) < 10:
                continue
            canon = url.split("?")[0]
            if canon in seen_urls:
                continue
            seen_urls.add(canon)
            rank += 1
            results.append(SearchResult(title=title, url=canon, rank=rank))
            if rank >= SETTINGS.max_serp_results:
                break

        if not results:
            results = salvage_bestbuy_serp_links(html, base_url)

        return results

    def parse_product(self, html: str, url: str) -> ProductFields:
        json_ld = self.parse_product_with_json_ld(html, url)
        soup = BeautifulSoup(html, "lxml")

        title = json_ld.title if json_ld else ""
        node = soup.select_one(".sku-title h1, h1.h4")
        if node:
            title = node.get_text(strip=True) or title

        price = json_ld.price if json_ld else None
        if not price:
            pnode = soup.select_one(
                "[data-testid='customer-price'] span, .priceView-customer-price span"
            )
            if pnode:
                price = parse_price(pnode.get_text())

        rating = json_ld.average_rating if json_ld else None
        if not rating:
            rnode = soup.select_one(".c-ratings-reviews, .ugc-c-ratings-reviews")
            if rnode:
                rating = parse_rating(rnode.get_text())

        reviews = json_ld.review_count if json_ld else None
        if not reviews:
            rv = soup.select_one(".c-reviews, [itemprop='reviewCount']")
            if rv:
                reviews = parse_review_count(rv.get_text())

        if not title or not price:
            raise ExtractionFailure("could not parse bestbuy product fields")

        return ProductFields(
            title=title,
            price=price,
            average_rating=rating,
            review_count=reviews,
        )
