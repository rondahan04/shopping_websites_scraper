"""Newegg.com adapter."""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from config import SETTINGS
from models import ExtractionFailure, ProductFields, SearchResult
from sites.base import SiteAdapter
from utils.parsing import absolute_url, is_same_domain, parse_price, parse_rating, parse_review_count

_NEWEGG_ITEM_RE = re.compile(r"(?:Item=|item=)([A-Z0-9-]{6,})", re.I)
_NEWEGG_P_SEG_RE = re.compile(r"/p/([A-Z0-9][A-Z0-9-]{3,})", re.I)


def _newegg_product_segment(url: str) -> str | None:
    parsed = urlparse(url)
    path = (parsed.path or "").lower()
    if path.endswith("/p/pl") or "/p/pl/" in path:
        return None
    m = _NEWEGG_P_SEG_RE.search(parsed.path or "")
    if m:
        seg = m.group(1).lower()
        if seg not in ("pl", "pls"):
            return m.group(1)
    qs = parsed.query or ""
    im = _NEWEGG_ITEM_RE.search(qs)
    if im:
        return im.group(1)
    return None


_NEWEGG_ACCESSORY_SLUGS = (
    "case",
    "keyboard",
    "cover",
    "folio",
    "protector",
    "charger",
    "cable",
    "mount",
    "bag",
    "sleeve",
    "backpack",
    "carrying-case",
    "screen-protector",
)


def _newegg_url_looks_like_accessory(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(slug in path for slug in _NEWEGG_ACCESSORY_SLUGS)


def salvage_newegg_serp_links(html: str, base_url: str) -> list[SearchResult]:
    """Recover PDP links from Firecrawl / script-heavy SERP HTML."""
    seen: set[str] = set()
    out: list[SearchResult] = []
    rank = 0
    patterns = (
        r"https://(?:www\.)?newegg\.com/(?:[^\s\"'<>]*?Item=[A-Z0-9-]{6,}[^\s\"'<>]*)",
        r"https://(?:www\.)?newegg\.com/[^/\s\"'<>]+/p/[A-Z0-9][A-Z0-9-]{3,}(?:[^\s\"'<>]*)?",
        r"https://(?:www\.)?newegg\.com/p/[A-Z0-9][A-Z0-9-]{3,}(?:/[^\s\"'<>]*)?",
        r'["\'](/[^"\']+/p/[A-Z0-9][A-Z0-9-]{3,}[^"\']*)["\']',
        r'["\'](/p/[A-Z0-9][A-Z0-9-]{3,}[^"\']*)["\']',
        r'Item=([A-Z0-9-]{8,})',
    )
    for pat in patterns:
        for m in re.finditer(pat, html, re.I):
            raw = m.group(1) if m.lastindex else m.group(0)
            if raw.startswith("Item=") or (m.lastindex and not raw.startswith("http")):
                if raw.startswith("Item="):
                    code = raw.split("=", 1)[1]
                else:
                    code = raw
                url = f"https://www.newegg.com/Product.aspx?Item={code}"
            elif raw.startswith("/"):
                url = absolute_url(base_url, raw.split('"')[0])
            else:
                url = raw.split('"')[0].split("#")[0].strip()
            if not is_same_domain(url, "newegg.com"):
                continue
            if _newegg_product_segment(url) is None:
                continue
            if _newegg_url_looks_like_accessory(url):
                continue
            canon = url.split("?")[0] if "Item=" not in url else url.split("#")[0]
            key = canon.lower()
            if key in seen:
                continue
            seen.add(key)
            seg = _newegg_product_segment(url) or "product"
            title = f"Newegg {seg}"
            rank += 1
            out.append(SearchResult(title=title, url=url.split("#")[0], rank=rank))
            if rank >= SETTINGS.max_serp_results:
                return out
    return out


class NeweggAdapter(SiteAdapter):
    display_name = "Newegg.com"
    domain = "newegg.com"

    def build_search_url(self, query: str) -> str:
        return f"https://www.newegg.com/p/pl?d={self.encoded_query(query)}"

    def is_product_url(self, url: str) -> bool:
        if not is_same_domain(url, self.domain):
            return False
        return _newegg_product_segment(url) is not None

    def parse_search_results(self, html: str, base_url: str) -> list[SearchResult]:
        soup = BeautifulSoup(html, "lxml")
        results: list[SearchResult] = []
        rank = 0
        seen_urls: set[str] = set()

        for a in soup.select("a.item-title[href]"):
            title = a.get_text(strip=True)
            href = unescape(a.get("href", ""))
            if len(title) < 8 or not href:
                continue
            url = absolute_url(base_url, href).split("#")[0]
            if "Item=" not in href:
                url = url.split("?")[0]
            if not self.is_product_url(url) or _newegg_url_looks_like_accessory(url):
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)
            rank += 1
            results.append(SearchResult(title=title, url=url, rank=rank))
            if rank >= SETTINGS.max_serp_results:
                return results

        for row in soup.select(
            ".item-cell, "
            ".list-wrap .item-container, "
            "div.item-container:not(.combo-item-cell), "
            "tr[class*='item'], "
            "div.cell-inner"
        ):
            classes = row.get("class") or []
            cls = " ".join(classes).lower()
            if "sponsored" in cls or row.select_one("[class*='sponsored'], .combo-item-cell"):
                continue
            link = row.select_one(
                "a.item-title, "
                "a[class*='itemTitle'], "
                ".item-info > a.item-title, "
                "a[itemprop='url'], "
                ".item-info a.btn-link"
            )
            if not link:
                continue
            title = link.get_text(strip=True)
            href = unescape(link.get("href", ""))
            if not title or not href:
                continue
            url = absolute_url(base_url, href).split("#")[0]
            if "Item=" in href:
                url = absolute_url(base_url, href)
            else:
                url = url.split("?")[0]
            if not self.is_product_url(url):
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)
            rank += 1
            results.append(SearchResult(title=title, url=url, rank=rank))
            if rank >= SETTINGS.max_serp_results:
                break

        if not results:
            for a in soup.select('a[href*="/p/"], a[href*="Item="]'):
                title = a.get_text(strip=True)
                href = unescape(a.get("href", ""))
                if len(title) < 8:
                    continue
                url = absolute_url(base_url, href)
                if "Item=" not in href:
                    url = url.split("?")[0]
                if not self.is_product_url(url):
                    continue
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                rank += 1
                results.append(SearchResult(title=title, url=url, rank=rank))
                if rank >= SETTINGS.max_serp_results:
                    break

        if not results:
            for a in soup.select("a.item-img[href], a[href].item-img"):
                img = a.select_one("img[title], img[alt]")
                if not img:
                    continue
                title = (img.get("title") or img.get("alt") or "").strip()
                if len(title) < 12:
                    continue
                href = a.get("href", "")
                url = absolute_url(base_url, href).split("&amp;")[0].split("#")[0]
                if not self.is_product_url(url) or _newegg_url_looks_like_accessory(url):
                    continue
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                rank += 1
                results.append(SearchResult(title=title, url=url, rank=rank))
                if rank >= SETTINGS.max_serp_results:
                    break

        if not results:
            results = salvage_newegg_serp_links(html, base_url)

        return results

    def parse_product(self, html: str, url: str) -> ProductFields:
        json_ld = self.parse_product_with_json_ld(html, url)
        soup = BeautifulSoup(html, "lxml")

        title = json_ld.title if json_ld else ""
        node = soup.select_one("h1.product-title, h1[itemprop='name']")
        if node:
            title = node.get_text(strip=True) or title

        price = json_ld.price if json_ld else None
        if not price:
            pnode = soup.select_one(
                ".price-current strong, .product-price, [itemprop='price']"
            )
            if pnode:
                price = parse_price(
                    pnode.get("content") or pnode.get_text()
                )

        rating = json_ld.average_rating if json_ld else None
        reviews = json_ld.review_count if json_ld else None
        if not rating:
            rnode = soup.select_one("i.rating, [itemprop='ratingValue']")
            if rnode:
                rating = parse_rating(rnode.get_text())
        if not reviews:
            rv = soup.select_one(".item-rating-num, [itemprop='reviewCount']")
            if rv:
                reviews = parse_review_count(rv.get_text())

        if not title or not price:
            raise ExtractionFailure("could not parse newegg product fields")

        return ProductFields(
            title=title,
            price=price,
            average_rating=rating,
            review_count=reviews,
        )
