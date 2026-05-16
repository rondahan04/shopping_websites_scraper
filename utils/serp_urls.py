"""Normalize and coerce SERP / LLM product URLs for retailer adapters."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from sites.base import SiteAdapter

_BB_SKU_IN_PATH = re.compile(r"/(\d{6,})(?:\.p)?(?:/|$|\?)", re.I)
_NEWEGG_ITEM = re.compile(r"(?:Item=|item=)([A-Z0-9-]{6,})", re.I)
_NEWEGG_P_SEG = re.compile(r"/p/([A-Z0-9][A-Z0-9-]{3,})", re.I)


def normalize_retail_url(url: str) -> str:
    u = url.strip()
    if u.startswith("//"):
        u = "https:" + u
    for host in ("www.bestbuy.com", "www.newegg.com", "www.amazon.com", "www.walmart.com"):
        if u.startswith(f"http://{host}"):
            u = f"https://{host}" + u[len(f"http://{host}") :]
    if u.startswith("http://bestbuy.com"):
        u = "https://www.bestbuy.com" + u[len("http://bestbuy.com") :]
    if u.startswith("https://bestbuy.com"):
        u = "https://www.bestbuy.com" + u[len("https://bestbuy.com") :]
    return u


def coerce_serp_product_url(url: str, adapter: SiteAdapter, *, search_url: str = "") -> str:
    """Turn partial / malformed LLM or embedded URLs into a canonical PDP URL when possible."""
    raw = (url or "").strip()
    if not raw:
        return raw

    # Bare numeric SKU (common LLM mistake for Best Buy).
    if adapter.domain == "bestbuy.com" and re.fullmatch(r"\d{6,}", raw):
        return f"https://www.bestbuy.com/site/product/{raw}.p"

    u = normalize_retail_url(raw)
    if not u.startswith("http"):
        if adapter.domain == "bestbuy.com" and raw.startswith("/site/"):
            u = f"https://www.bestbuy.com{raw}"
        elif adapter.domain == "newegg.com" and raw.startswith("/"):
            u = f"https://www.newegg.com{raw}"
        elif adapter.domain == "newegg.com":
            m = _NEWEGG_ITEM.search(raw)
            if m:
                return f"https://www.newegg.com/Product.aspx?Item={m.group(1)}"

    u = normalize_retail_url(u)

    if adapter.domain == "bestbuy.com":
        parsed = urlparse(u)
        if "/product/" in (parsed.path or "").lower() and not parsed.path.endswith("/"):
            return u.split("#")[0].strip()
        q = parse_qs(parsed.query)
        sku = (q.get("skuId") or q.get("skuid") or [None])[0]
        if sku and sku.isdigit() and len(sku) >= 6:
            if ".p" not in (parsed.path or ""):
                path = parsed.path.rstrip("/") or "/site/product"
                if not _BB_SKU_IN_PATH.search(path):
                    u = f"https://www.bestbuy.com{path}/{sku}.p"
        if "bestbuy.com" in u and ".p" not in u and _BB_SKU_IN_PATH.search(u):
            path = urlparse(u).path
            if path and not path.endswith(".p"):
                m = _BB_SKU_IN_PATH.search(path)
                if m and not path.endswith(f"{m.group(1)}.p"):
                    u = u.split("?")[0].rstrip("/") + ".p"

    if adapter.domain == "newegg.com":
        if "newegg.com" not in u.lower():
            m = _NEWEGG_ITEM.search(raw) or _NEWEGG_ITEM.search(u)
            if m:
                return f"https://www.newegg.com/Product.aspx?Item={m.group(1)}"
        parsed = urlparse(u)
        path = parsed.path or ""
        if "/p/pl" in path.lower() or path.lower().endswith("/p/pl"):
            m = _NEWEGG_P_SEG.search(search_url or "") or _NEWEGG_P_SEG.search(raw)
            if m and m.group(1).lower() not in ("pl", "pls"):
                return f"https://www.newegg.com/p/{m.group(1)}"

    return u.split("#")[0].strip()
