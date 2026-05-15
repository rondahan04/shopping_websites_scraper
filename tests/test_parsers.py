"""Parser tests using HTML fixtures."""

from decimal import Decimal

import pytest

from sites.amazon import AmazonAdapter
from sites.bestbuy import BestBuyAdapter
from sites.newegg import NeweggAdapter
from sites.walmart import WalmartAdapter
from tests.conftest import load_fixture


@pytest.mark.parametrize(
    "adapter_cls, serp_file, base_url, expected_title_fragment",
    [
        (AmazonAdapter, "amazon_serp.html", "https://www.amazon.com/s?k=test", "P12"),
        (BestBuyAdapter, "bestbuy_serp.html", "https://www.bestbuy.com/site/searchpage.jsp", "P12"),
        (WalmartAdapter, "walmart_serp.html", "https://www.walmart.com/search?q=test", "P12"),
        (NeweggAdapter, "newegg_serp.html", "https://www.newegg.com/p/pl?d=test", "P12"),
    ],
)
def test_parse_search_results(adapter_cls, serp_file, base_url, expected_title_fragment):
    adapter = adapter_cls()
    html = load_fixture(serp_file)
    results = adapter.parse_search_results(html, base_url)
    assert len(results) >= 1
    assert expected_title_fragment in results[0].title
    assert adapter.is_product_url(results[0].url)


@pytest.mark.parametrize(
    "adapter_cls, product_file, product_url",
    [
        (AmazonAdapter, "amazon_product.html", "https://www.amazon.com/dp/B0TEST123"),
        (BestBuyAdapter, "bestbuy_product.html", "https://www.bestbuy.com/site/lenovo/123.p"),
        (WalmartAdapter, "walmart_product.html", "https://www.walmart.com/ip/lenovo/123"),
        (NeweggAdapter, "newegg_product.html", "https://www.newegg.com/lenovo-tab/p/N82E168"),
    ],
)
def test_parse_product(adapter_cls, product_file, product_url):
    adapter = adapter_cls()
    fields = adapter.parse_product(load_fixture(product_file), product_url)
    assert "P12" in fields.title or "Lenovo" in fields.title
    assert fields.price is not None and fields.price > Decimal("0")
