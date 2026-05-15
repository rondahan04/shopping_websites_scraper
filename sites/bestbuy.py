"""BestBuy.com adapter."""

from __future__ import annotations

from bs4 import BeautifulSoup

from config import SETTINGS
from models import ExtractionFailure, ProductFields, SearchResult
from sites.base import SiteAdapter
from utils.parsing import absolute_url, is_same_domain, parse_price, parse_rating, parse_review_count


class BestBuyAdapter(SiteAdapter):
    display_name = "BestBuy.com"
    domain = "bestbuy.com"

    def build_search_url(self, query: str) -> str:
        return f"https://www.bestbuy.com/site/searchpage.jsp?st={self.encoded_query(query)}"

    def is_product_url(self, url: str) -> bool:
        return is_same_domain(url, self.domain) and "/site/" in url and ".p" in url

    def parse_search_results(self, html: str, base_url: str) -> list[SearchResult]:
        soup = BeautifulSoup(html, "lxml")
        results: list[SearchResult] = []
        rank = 0

        for item in soup.select("li.sku-item, .sku-item"):
            if item.select_one(".sponsored, [data-testid*='sponsor']"):
                continue
            link = item.select_one("h4.sku-title a, a[data-testid='product-title']")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if not title or not href:
                continue
            url = absolute_url(base_url, href)
            if not self.is_product_url(url):
                continue
            rank += 1
            results.append(SearchResult(title=title, url=url.split("?")[0], rank=rank))
            if rank >= SETTINGS.max_serp_results:
                break
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
