"""Configuration and environment-backed settings."""

from __future__ import annotations

import os
from dataclasses import dataclass

from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent

os.environ.setdefault(
    "PLAYWRIGHT_BROWSERS_PATH",
    str(_PROJECT_ROOT / ".playwright-browsers"),
)

# Project .env, then parent assignment folder (common layout for this repo).
load_dotenv(_PROJECT_ROOT / ".env")
load_dotenv(_PROJECT_ROOT.parent / ".env")


@dataclass(frozen=True)
class Settings:
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    search_timeout_s: float = 20.0
    product_timeout_s: float = 30.0
    playwright_timeout_ms: int = 35_000
    min_match_score: float = 48.0
    # When the best SERP row is slightly below min_match_score but model tokens align, still accept.
    min_match_score_soft_floor: float = 42.0
    ambiguity_delta: float = 5.0
    max_serp_results: int = 15
    llm_max_chars: int = 20_000
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.5"
    firecrawl_api_key: str | None = None
    firecrawl_api_url: str = "https://api.firecrawl.dev/v1/scrape"
    max_workers: int = 4
    # After all sites return: mean of successful prices; rescrape sites farther than this (e.g. 0.30 = 30%).
    price_gap_rescrape_threshold: float = 0.30
    price_gap_min_priced_sites: int = 2
    price_gap_rescrape_enabled: bool = True
    # HTTP(S) proxy with US egress — retried when price is missing (geo-blocked PDPs).
    usa_http_proxy: str | None = None
    usa_geo_retry_enabled: bool = True

    @classmethod
    def from_env(cls) -> Settings:
        firecrawl_key = os.getenv("FIRECRAWL_API_KEY") or os.getenv("FIRECRAWL_APY_KEY")
        t_raw = os.getenv("PRICE_GAP_RESCRAPE_THRESHOLD", "").strip()
        try:
            price_gap_threshold = float(t_raw) if t_raw else 0.30
        except ValueError:
            price_gap_threshold = 0.30
        min_sites_raw = os.getenv("PRICE_GAP_MIN_PRICED_SITES", "2").strip()
        try:
            min_priced = max(2, int(min_sites_raw))
        except ValueError:
            min_priced = 2
        rescrape_env = os.getenv("PRICE_GAP_RESCRAPE", "true").strip().lower()
        rescrape_on = rescrape_env not in ("0", "false", "no", "off")
        soft_raw = os.getenv("MIN_MATCH_SCORE_SOFT_FLOOR", "").strip()
        try:
            soft_floor = float(soft_raw) if soft_raw else 42.0
        except ValueError:
            soft_floor = 42.0
        soft_floor = min(soft_floor, 47.9)  # must stay strictly below min_match_score default
        usa_proxy = (
            os.getenv("USA_HTTP_PROXY")
            or os.getenv("US_HTTP_PROXY")
            or os.getenv("USA_PROXY_URL")
            or ""
        ).strip() or None
        usa_retry_env = os.getenv("USA_GEO_RETRY", "true").strip().lower()
        usa_retry_on = usa_retry_env not in ("0", "false", "no", "off")
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            firecrawl_api_key=firecrawl_key,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5.5"),
            price_gap_rescrape_threshold=price_gap_threshold,
            price_gap_min_priced_sites=min_priced,
            price_gap_rescrape_enabled=rescrape_on,
            min_match_score_soft_floor=soft_floor,
            usa_http_proxy=usa_proxy,
            usa_geo_retry_enabled=usa_retry_on,
        )


SETTINGS = Settings.from_env()

GENERIC_BOT_PATTERNS = [
    r"captcha",
    r"robot\s*check",
    r"unusual\s+traffic",
    r"access\s+denied",
    r"are\s+you\s+a\s+human",
    r"verify\s+you\s+are\s+human",
    r"cf-browser-verification",
    r"challenge-platform",
    r"please\s+enable\s+javascript",
    r"automated\s+access",
]
