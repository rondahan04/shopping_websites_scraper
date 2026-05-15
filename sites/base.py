"""Base site adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from models import ProductFields, SearchResult
from utils.parsing import (
    extract_json_ld_products,
    fields_from_json_ld,
    parse_price,
    parse_rating,
    parse_review_count,
)


class SiteAdapter(ABC):
    display_name: str
    domain: str

    @abstractmethod
    def build_search_url(self, query: str) -> str: ...

    @abstractmethod
    def parse_search_results(self, html: str, base_url: str) -> list[SearchResult]: ...

    @abstractmethod
    def is_product_url(self, url: str) -> bool: ...

    def bot_check_patterns(self) -> list[str]:
        return []

    @abstractmethod
    def parse_product(self, html: str, url: str) -> ProductFields: ...

    def parse_product_with_json_ld(self, html: str, url: str) -> ProductFields | None:
        soup = BeautifulSoup(html, "lxml")
        for product in extract_json_ld_products(soup):
            title, price, rating, reviews = fields_from_json_ld(product)
            if title and price:
                return ProductFields(
                    title=title.strip(),
                    price=price,
                    average_rating=rating,
                    review_count=reviews,
                )
        return None

    @staticmethod
    def encoded_query(query: str) -> str:
        return quote_plus(query.strip())
