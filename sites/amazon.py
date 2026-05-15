"""Amazon.com adapter."""

from __future__ import annotations

import re
from decimal import Decimal
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from config import SETTINGS
from models import ExtractionFailure, ProductFields, SearchResult
from sites.base import SiteAdapter
from utils.parsing import absolute_url, is_same_domain, parse_price, parse_rating, parse_review_count


_ADDON_PRICE_CONTEXT_NEEDLES = (
    "trade-in",
    "tradein",
    "protect",
    "insurance",
    "warranty-",
    "warranty_",
    "subscription",
    "monthly",
    "protection-plan",
    "applecare",
    "installment",
    "financing",
)


def _price_text_looks_like_financing_teaser(text: str) -> bool:
    t = text.lower().replace(" ", "").replace("\u00a0", "")
    if "/mo" in t or "/month" in t or "permonth" in t or "amonth" in t:
        return True
    if "monthly" in text.lower() and any(ch.isdigit() for ch in text):
        return True
    return False


_FINANCING_PARENT_RE = re.compile(
    r"(?:/|\bper)\s*mo\b|/month\b|"
    r"\bmonthly\s+payments?\b|\bpayments?\s+of\b|"
    r"\bestimated\s+payment\b|\bno\s+cost\s+emi\b|"
    r"\bqualifying\s+installments?\b",
    re.I,
)


def _amazon_offscreen_in_financing_context(span: Tag) -> bool:
    """True when a small off-screen dollar amount sits next to ``/mo`` / ``per month`` copy.

    Do not walk the entire buy box: a legitimate ``$1,599.00`` line shares an ancestor with a
    financing teaser and would be discarded if any ancestor matched ``/mo``.
    """
    raw = span.get_text(strip=True)
    if _price_text_looks_like_financing_teaser(raw):
        return False
    p = parse_price(raw)
    if not p or p >= Decimal("150"):
        return False
    cur: Tag | None = span.parent
    for _ in range(4):
        if cur is None:
            break
        blob = cur.get_text(" ", strip=True).lower()
        if len(blob) > 240:
            break
        collapsed = blob.replace(" ", "").replace("\u00a0", "")
        if ("/mo" in collapsed or "/month" in collapsed or "permonth" in collapsed) and (
            _FINANCING_PARENT_RE.search(blob) or "month" in collapsed
        ):
            return True
        cur = cur.parent
    return False


def _amazon_collect_valid_prices(root: Tag | BeautifulSoup) -> list[Decimal]:
    """Collect parseable buy-box style prices under ``root``, skipping teasers and add-on rows."""
    needles: list[Decimal] = []
    for span in root.select(
        "span.a-price span.a-offscreen, .a-price .a-offscreen, .priceToPay .a-offscreen"
    ):
        if _price_node_in_addon_context(span):
            continue
        raw = span.get_text()
        if _price_text_looks_like_financing_teaser(raw):
            continue
        if _amazon_offscreen_in_financing_context(span):
            continue
        p = parse_price(raw)
        if p:
            needles.append(p)
    return needles


_AMAZON_LAPTOP_TITLE_RE = re.compile(r"macbook\s+(?:pro|air)\b", re.I)


def _amazon_laptop_price_implausibly_low(title: str, price: Decimal) -> bool:
    """MacBook listings below ~$400 are almost never the cash buy-box (financing fragment)."""
    if not title.strip():
        return False
    if not _AMAZON_LAPTOP_TITLE_RE.search(title):
        return False
    return price < Decimal("400")


def _amazon_whole_page_offscreen_price_max(soup: BeautifulSoup) -> Decimal | None:
    """Largest plausible cash price from any ``.a-offscreen`` on the PDP (last resort)."""
    found = _amazon_collect_valid_prices(soup)
    return max(found) if found else None


def _amazon_rescue_high_price_from_offer_regions(soup: BeautifulSoup) -> Decimal | None:
    """Re-scan known offer containers (including ``#centerCol``) after a suspiciously low laptop price."""
    extra_selectors = (
        "#bookPrice_feature_div",
        "#buyNew_noncbb",
        "#centerCol",
    )
    collected: list[Decimal] = []
    for sel in _AMAZON_PRIMARY_PRICE_ROOTS + extra_selectors:
        el = soup.select_one(sel)
        if el:
            collected.extend(_amazon_collect_valid_prices(el))
    return max(collected) if collected else None


_AMAZON_PRIMARY_PRICE_ROOTS = (
    "#corePrice_feature_div",
    "#corePrice_desktop",
    "#apex_desktop_offerDisplay_feature_div",
    "#apex_offerDisplay_desktop",
    "#unifiedPrice_feature_div",
)


def _price_node_in_addon_context(node: Tag) -> bool:
    cur: Tag | None = node
    for _ in range(10):
        if cur is None:
            break
        ident_parts: list[str] = []
        if cur.get("id"):
            ident_parts.append(str(cur.get("id")))
        for c in cur.get("class") or []:
            ident_parts.append(str(c))
        bucket = " ".join(ident_parts).lower()
        for needle in _ADDON_PRICE_CONTEXT_NEEDLES:
            if needle in bucket:
                return True
        cur = cur.parent
    return False


def _amazon_best_dom_price(soup: BeautifulSoup) -> Decimal | None:
    """Prefer canonical offer blocks (``#corePrice_*``) before the wider buy box.

    Amazon sometimes nests a low secondary offer (refurb, coupon line) only under
    ``#desktop_buybox`` while the real new price lives under ``#corePrice_feature_div``.
    Scanning only the first buy-box root used to take ``max()`` of the wrong subset.
    """
    for sel in _AMAZON_PRIMARY_PRICE_ROOTS:
        el = soup.select_one(sel)
        if el:
            primary = _amazon_collect_valid_prices(el)
            if primary:
                return max(primary)

    # Collect from every present layout root. Stopping at the first match hid the real
    # cash price in ``#centerCol`` when ``#desktop_buybox`` only carried a financing line.
    roots: list[BeautifulSoup | Tag] = []
    for sel in ("#desktop_buybox", "#tabular-buybox", "#centerCol"):
        el = soup.select_one(sel)
        if el:
            roots.append(el)
    if not roots:
        roots.append(soup)
    needles: list[Decimal] = []
    for root in roots:
        needles.extend(_amazon_collect_valid_prices(root))
    return max(needles) if needles else None

_DP_OR_GP_ASIN_RE = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})", re.I)


def _asin_from_data_attr(card: Tag) -> str | None:
    raw = (card.get("data-asin") or "").strip()
    if len(raw) == 10 and re.fullmatch(r"[A-Za-z0-9]{10}", raw):
        return raw.upper()
    return None


def _href_contains_asin(href: str, asin: str) -> bool:
    hits = _DP_OR_GP_ASIN_RE.findall(href or "")
    return asin.upper() in {x.upper() for x in hits}


def amazon_heading_conflicts_with_ram_module_slug(url_path: str, title: str) -> bool:
    """Detect Amazon SERP glue: laptop-ish SERP heading vs RAM kit canonical URL slug."""
    norm = url_path.lower().replace("\\", "/")
    if "apple-macbook-memory" not in norm and "apple-mac-mini-memory" not in norm:
        return False
    tl = title.lower()
    laptop_family = "macbook pro" in tl or "macbook air" in tl
    looks_configured_laptop = bool(
        re.search(r"\bm\s*\d+", tl)
        or re.search(r"\b\d+\s*-?\s*inch\b|\d+\"", tl)
    )
    return laptop_family and looks_configured_laptop


def _scoped_title_dp_for_asin(card: Tag, asin: str) -> Tag | None:
    """Title-adjacent /dp/ link whose href carries the listing ASIN (avoids carousel noise)."""
    for link in card.select("h2 a, span[data-cy='title-recipe'] a"):
        href = link.get("href") or ""
        if _href_contains_asin(href, asin):
            return link
    return None


def _gather_h2_dp_links(card: Tag) -> list[Tag]:
    seen: list[Tag] = []
    vis: set[int] = set()
    for h in card.select("h2"):
        for link in h.select("a[href*='/dp/'], a[href*='/gp/product/']"):
            if link.get("href") and id(link) not in vis:
                seen.append(link)
                vis.add(id(link))
    return seen


def _amazon_card_title_link(card: Tag) -> Tag | None:
    """Prefer the SERP title anchor under h2; align with listing ``data-asin`` when possible."""
    card_asin = _asin_from_data_attr(card)
    preferred: list[Tag] = _gather_h2_dp_links(card)
    recipe = (
        card.select_one("span[data-cy='title-recipe'] a[href*='/dp/']")
        or card.select_one("span[data-cy='title-recipe'] a[href*='/gp/product/']")
    )
    if recipe and recipe.get("href"):
        preferred.append(recipe)

    if card_asin:
        for link in preferred:
            href = link.get("href") or ""
            if _href_contains_asin(href, card_asin):
                return link
        scoped = _scoped_title_dp_for_asin(card, card_asin)
        if scoped:
            return scoped

    for link in preferred:
        return link

    recipe_only = (
        card.select_one("span[data-cy='title-recipe'] a[href*='/dp/']")
        or card.select_one("span[data-cy='title-recipe'] a[href*='/gp/product/']")
    )
    return recipe_only


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
            link_el = _amazon_card_title_link(card)
            if not link_el:
                continue
            title = link_el.get_text(strip=True)
            href = link_el.get("href")
            if not title or not href:
                continue
            url = absolute_url(base_url, href)
            if not self.is_product_url(url):
                continue
            path_only = urlparse(url).path
            if amazon_heading_conflicts_with_ram_module_slug(path_only, title):
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

        price = _amazon_best_dom_price(soup)
        if not price:
            for sel in (
                "#corePrice_feature_div .a-offscreen",
                ".priceToPay span.a-offscreen",
                "#priceblock_ourprice",
                "#priceblock_dealprice",
            ):
                node = soup.select_one(sel)
                if node and not _price_node_in_addon_context(node):
                    raw = node.get_text()
                    if _price_text_looks_like_financing_teaser(raw):
                        continue
                    if _amazon_offscreen_in_financing_context(node):
                        continue
                    price = parse_price(raw)
                    if price:
                        break
        if not price:
            for node in soup.select("span.a-price span.a-offscreen, .a-price .a-offscreen"):
                if _price_node_in_addon_context(node):
                    continue
                raw = node.get_text()
                if _price_text_looks_like_financing_teaser(raw):
                    continue
                if _amazon_offscreen_in_financing_context(node):
                    continue
                price = parse_price(raw)
                if price:
                    break
        if not price and json_ld and json_ld.price:
            # ``Offer.price`` on Apple laptops is often the monthly installment, not MSRP.
            if not (
                _AMAZON_LAPTOP_TITLE_RE.search(title or "")
                and json_ld.price < Decimal("150")
            ):
                price = json_ld.price
        if not price:
            price = _amazon_rescue_high_price_from_offer_regions(soup)

        # If JSON-LD carries a materially higher offer than DOM, trust JSON-LD. Low DOM often
        # comes from a lone refurb/accessory line in ``#desktop_buybox`` when ``#corePrice_*``
        # was absent from the fetched HTML. When JSON-LD is a financing/monthly fragment it
        # stays below DOM * 1.35 so we keep DOM (see ``amazon_product_json_ld_trap`` fixture).
        if price and json_ld and json_ld.price:
            jp = json_ld.price
            if jp > price * Decimal("1.35"):
                price = jp

        # Schema.org ``Offer`` price can mirror a monthly installment; widen DOM search when
        # the title is clearly a MacBook but the resolved price looks like a payment fragment.
        if price and title and _amazon_laptop_price_implausibly_low(title, price):
            rescue = _amazon_rescue_high_price_from_offer_regions(soup)
            if rescue and rescue > price * Decimal("1.35"):
                price = rescue
            elif json_ld and json_ld.price and json_ld.price > price * Decimal("1.35"):
                price = json_ld.price
            elif (
                (whole := _amazon_whole_page_offscreen_price_max(soup))
                and whole > price * Decimal("1.15")
            ):
                price = whole

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
