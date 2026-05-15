"""Amazon.com adapter."""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from config import SETTINGS
from models import ExtractionFailure, ProductFields, SearchResult
from sites.base import SiteAdapter
from utils.parsing import absolute_url, is_same_domain, parse_price, parse_rating, parse_review_count


class AmazonAdapter(SiteAdapter):
    display_name = "Amazon.com"
    domain = "amazon.com"

    def build_search_url(self, query: str) -> str:
        return f"https://www.amazon.com/s?k={self.encoded_query(query)}"

    def bot_check_patterns(self) -> list[str]:
        return [r"api-services-support@amazon\.com", r"/errors/validatecaptcha"]

    def is_product_url(self, url: str) -> bool:
        return is_same_domain(url, self.domain) and (
            "/dp/" in url or "/gp/product/" in url
        )

    def parse_search_results(self, html: str, base_url: str) -> list[SearchResult]:
        soup = BeautifulSoup(html, "lxml")
        results: list[SearchResult] = []
        rank = 0

        for card in soup.select(
            '[data-component-type="s-search-result"], '
            'div.s-result-item[data-asin], '
            'div[role="listitem"][data-asin]'
        ):
            if card.select_one(
                '[data-component-type="sp-sponsored-result"], '
                ".puis-sponsored-label-text, "
                "[aria-label*='Sponsored']"
            ):
                continue
            h2 = card.select_one(
                "h2 a, h2 span a, a.a-link-normal[href*='/dp/'], span[data-cy='title-recipe'] a"
            )
            if not h2:
                continue
            title = h2.get_text(strip=True)
            href = h2.get("href")
            if not title or not href:
                continue
            url = absolute_url(base_url, href)
            if not self.is_product_url(url):
                continue
            rank += 1
            results.append(SearchResult(title=title, url=url.split("?")[0], rank=rank))
            if rank >= SETTINGS.max_serp_results:
                break

        if not results:
            for a in soup.select('a[href*="/dp/"]'):
                title = a.get_text(strip=True)
                href = a.get("href", "")
                if len(title) < 10:
                    continue
                url = absolute_url(base_url, href).split("?")[0]
                if self.is_product_url(url):
                    rank += 1
                    results.append(SearchResult(title=title, url=url, rank=rank))
                if rank >= SETTINGS.max_serp_results:
                    break
        return results

    def parse_product(self, html: str, url: str) -> ProductFields:
        json_ld = self.parse_product_with_json_ld(html, url)
        soup = BeautifulSoup(html, "lxml")

        title = ""
        if json_ld:
            title = json_ld.title
        el = soup.select_one("#productTitle")
        if el:
            title = el.get_text(strip=True) or title

        price = json_ld.price if json_ld else None
        if not price:
            for sel in (
                ".a-price .a-offscreen",
                "#priceblock_ourprice",
                "#priceblock_dealprice",
                ".priceToPay span.a-offscreen",
                "#corePrice_feature_div .a-offscreen",
            ):
                node = soup.select_one(sel)
                if node:
                    price = parse_price(node.get_text())
                    if price:
                        break

        rating = json_ld.average_rating if json_ld else None
        if not rating:
            rnode = soup.select_one("#acrPopover, span[data-hook='rating-out-of-text']")
            if rnode:
                rating = parse_rating(rnode.get_text())

        reviews = json_ld.review_count if json_ld else None
        if not reviews:
            rv = soup.select_one("#acrCustomerReviewText")
            if rv:
                reviews = parse_review_count(rv.get_text())

        if not title or not price:
            raise ExtractionFailure("could not parse amazon product fields")

        return ProductFields(
            title=title,
            price=price,
            average_rating=rating,
            review_count=reviews,
        )
