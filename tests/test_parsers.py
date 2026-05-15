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


def test_amazon_serp_prefers_h2_title_dp_over_earlier_dp_in_card():
    # Regression: comma-joined CSS on the card could grab the first /dp/ in DOM order
    # (e.g. accessory) instead of the SERP title link under h2.
    adapter = AmazonAdapter()
    html = load_fixture("amazon_serp_dom_order_trap.html")
    results = adapter.parse_search_results(html, "https://www.amazon.com/s?k=test")
    assert len(results) >= 1
    assert "B0NOTMEMORY" in results[0].url
    assert "B0ACCESSORY" not in results[0].url
    assert "MacBook" in results[0].title


def test_amazon_skips_memory_module_slug_with_macbook_heading():
    adapter = AmazonAdapter()
    html = load_fixture("amazon_serp_memory_slug_trap.html")
    results = adapter.parse_search_results(html, "https://www.amazon.com/")
    assert len(results) >= 1
    assert "B0KEEPME" in results[0].url
    assert "B0BADLINK" not in results[0].url
    assert "Memory-512GB" not in results[0].url


def test_amazon_dom_price_beats_low_json_ld_offer():
    adapter = AmazonAdapter()
    fields = adapter.parse_product(
        load_fixture("amazon_product_json_ld_trap.html"),
        "https://www.amazon.com/dp/B0TESTMAC",
    )
    assert fields.price == Decimal("1999")


def test_bestbuy_accepts_pdp_urls_without_dot_p_when_numeric_sku():
    adapter = BestBuyAdapter()
    assert adapter.is_product_url("https://www.bestbuy.com/site/apple-macbook-pro/6534606")
    assert adapter.is_product_url(
        "https://www.bestbuy.com/site/apple-macbook-pro/6534606?skuId=6534606"
    )
    assert not adapter.is_product_url(
        "https://www.bestbuy.com/site/searchpage.jsp?st=macbook"
    )


def test_bestbuy_salvage_extracts_pdp_urls_from_embedded_json():
    adapter = BestBuyAdapter()
    html = """<html><body><script type="application/json">
    {"href":"https://www.bestbuy.com/site/lenovo-tab-p12-gray/6123456.p"}
    </script></body></html>"""
    results = adapter.parse_search_results(
        html, "https://www.bestbuy.com/site/searchpage.jsp?st=lenovo"
    )
    assert len(results) >= 1
    assert "6123456" in results[0].url
    assert adapter.is_product_url(results[0].url)


def test_bestbuy_salvage_accepts_bestbuy_host_without_www():
    adapter = BestBuyAdapter()
    html = """<html><body><script>
    {"url":"https://bestbuy.com/site/apple-macbook-pro-space-black/6534606.p"}
    </script></body></html>"""
    results = adapter.parse_search_results(
        html, "https://www.bestbuy.com/site/searchpage.jsp?st=macbook"
    )
    assert len(results) >= 1
    assert "6534606" in results[0].url
    assert adapter.is_product_url(results[0].url)


def test_amazon_parse_product_skips_monthly_financing_teaser_price():
    adapter = AmazonAdapter()
    fields = adapter.parse_product(
        load_fixture("amazon_product_financing_teaser.html"),
        "https://www.amazon.com/dp/B0FINANCE",
    )
    assert fields.price == Decimal("1599.00")


def test_amazon_prefers_core_price_div_when_buybox_shows_lower_teaser():
    adapter = AmazonAdapter()
    fields = adapter.parse_product(
        load_fixture("amazon_core_price_outside_buybox.html"),
        "https://www.amazon.com/dp/B0COREPRICE",
    )
    assert fields.price == Decimal("1999.00")


def test_amazon_max_price_across_buybox_and_center_col_when_no_core_price_root():
    """Regression: only scanning ``#desktop_buybox`` kept a financing fragment and missed MSRP in ``#centerCol``."""
    adapter = AmazonAdapter()
    fields = adapter.parse_product(
        load_fixture("amazon_buybox_vs_centercol_max.html"),
        "https://www.amazon.com/dp/B0DUALREGION",
    )
    assert fields.price == Decimal("1849.00")


def test_amazon_whole_page_max_when_core_price_shows_only_financing_like_line():
    """``#corePrice_*`` can show a low line while a higher list price exists elsewhere on the PDP."""
    adapter = AmazonAdapter()
    fields = adapter.parse_product(
        load_fixture("amazon_coreprice_teaser_msrp_elsewhere.html"),
        "https://www.amazon.com/dp/B0CORETEASE",
    )
    assert fields.price == Decimal("1849.00")


def test_amazon_json_ld_rescues_when_dom_buybox_only_low_offer():
    adapter = AmazonAdapter()
    fields = adapter.parse_product(
        load_fixture("amazon_json_ld_rescues_low_dom.html"),
        "https://www.amazon.com/dp/B0JSONRESCUE",
    )
    assert fields.price == Decimal("1999.00")


def test_amazon_skips_financing_offscreen_when_parent_mentions_per_month():
    adapter = AmazonAdapter()
    fields = adapter.parse_product(
        load_fixture("amazon_financing_offscreen_parent_context.html"),
        "https://www.amazon.com/dp/B0FINPARENT",
    )
    assert fields.price == Decimal("3241.00")
