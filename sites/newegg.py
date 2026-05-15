"""Newegg.com adapter."""

from __future__ import annotations

from bs4 import BeautifulSoup

from config import SETTINGS
from models import ExtractionFailure, ProductFields, SearchResult
from sites.base import SiteAdapter
from utils.parsing import absolute_url, is_same_domain, parse_price, parse_rating, parse_review_count


class NeweggAdapter(SiteAdapter):
    display_name = "Newegg.com"
    domain = "newegg.com"

    def build_search_url(self, query: str) -> str:
        return f"https://www.newegg.com/p/pl?d={self.encoded_query(query)}"

    def is_product_url(self, url: str) -> bool:
        return is_same_domain(url, self.domain) and (
            "/p/" in url or "Item=" in url
        )

    def parse_search_results(self, html: str, base_url: str) -> list[SearchResult]:
        soup = BeautifulSoup(html, "lxml")
        results: list[SearchResult] = []
        rank = 0
        seen_urls: set[str] = set()

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
            href = link.get("href", "")
            if not title or not href:
                continue
            url = absolute_url(base_url, href).split("?")[0]
            if not self.is_product_url(url) and "/p/" not in url:
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
                href = a.get("href", "")
                if len(title) < 8:
                    continue
                url = absolute_url(base_url, href).split("?")[0]
                if not self.is_product_url(url):
                    continue
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                rank += 1
                results.append(SearchResult(title=title, url=url, rank=rank))
                if rank >= SETTINGS.max_serp_results:
                    break

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
