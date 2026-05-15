"""Walmart.com adapter."""

from __future__ import annotations

from bs4 import BeautifulSoup

from config import SETTINGS
from models import ExtractionFailure, ProductFields, SearchResult
from sites.base import SiteAdapter
from utils.parsing import absolute_url, is_same_domain, parse_price, parse_rating, parse_review_count


class WalmartAdapter(SiteAdapter):
    display_name = "Walmart.com"
    domain = "walmart.com"

    def build_search_url(self, query: str) -> str:
        return f"https://www.walmart.com/search?q={self.encoded_query(query)}"

    def bot_check_patterns(self) -> list[str]:
        return [r"px-captcha", r"robot or human"]

    def is_product_url(self, url: str) -> bool:
        return is_same_domain(url, self.domain) and "/ip/" in url

    def parse_search_results(self, html: str, base_url: str) -> list[SearchResult]:
        soup = BeautifulSoup(html, "lxml")
        results: list[SearchResult] = []
        rank = 0

        for link in soup.select('a[link-identifier="itemClick"], a[href*="/ip/"]'):
            parent = link.find_parent(attrs={"data-item-id": True}) or link
            if parent and parent.select_one("[data-automation-id*='sponsored']"):
                continue
            title = link.get("aria-label") or link.get_text(strip=True)
            href = link.get("href", "")
            if not title or len(title) < 5 or not href:
                continue
            url = absolute_url(base_url, href).split("?")[0]
            if not self.is_product_url(url):
                continue
            if any(r.url == url for r in results):
                continue
            rank += 1
            results.append(SearchResult(title=title, url=url, rank=rank))
            if rank >= SETTINGS.max_serp_results:
                break
        return results

    def parse_product(self, html: str, url: str) -> ProductFields:
        json_ld = self.parse_product_with_json_ld(html, url)
        soup = BeautifulSoup(html, "lxml")

        title = json_ld.title if json_ld else ""
        node = soup.select_one("h1[itemprop='name'], h1#main-title")
        if node:
            title = node.get_text(strip=True) or title

        price = json_ld.price if json_ld else None
        if not price:
            pnode = soup.select_one(
                "[itemprop='price'], span[data-automation-id='product-price']"
            )
            if pnode:
                price = parse_price(
                    pnode.get("content") or pnode.get_text()
                )

        rating = json_ld.average_rating if json_ld else None
        reviews = json_ld.review_count if json_ld else None
        if not rating:
            rnode = soup.select_one("[itemprop='ratingValue'], span.rating-number")
            if rnode:
                rating = parse_rating(
                    rnode.get("content") or rnode.get_text()
                )
        if not reviews:
            rv = soup.select_one("[itemprop='reviewCount'], span.reviews-count")
            if rv:
                reviews = parse_review_count(
                    rv.get("content") or rv.get_text()
                )

        if not title or not price:
            raise ExtractionFailure("could not parse walmart product fields")

        return ProductFields(
            title=title,
            price=price,
            average_rating=rating,
            review_count=reviews,
        )
