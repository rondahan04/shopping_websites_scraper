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

# Random human-like pause range (seconds) after navigation / Firecrawl waitFor.
SETTLE_DELAY_MIN_S: float = 3.0
SETTLE_DELAY_MAX_S: float = 8.0


@dataclass(frozen=True)
class Settings:
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    search_timeout_s: float = 20.0
    product_timeout_s: float = 30.0
    playwright_timeout_ms: int = 35_000
    settle_delay_min_s: float = SETTLE_DELAY_MIN_S
    settle_delay_max_s: float = SETTLE_DELAY_MAX_S
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
    # Rescrape when scraped price differs from LLM reference by more than this (e.g. 0.20 = 20%).
    price_gap_rescrape_threshold: float = 0.20
    price_gap_rescrape_enabled: bool = True
    # Before PDP extract: GPT compares SERP title to LLM plan product_name.
    llm_title_verify_enabled: bool = True
    # After PDP extract: GPT judges whether scraped price is a plausible buy-box amount.
    llm_price_verify_enabled: bool = True

    @classmethod
    def from_env(cls) -> Settings:
        firecrawl_key = os.getenv("FIRECRAWL_API_KEY") or os.getenv("FIRECRAWL_APY_KEY")
        t_raw = os.getenv("PRICE_GAP_RESCRAPE_THRESHOLD", "").strip()
        try:
            price_gap_threshold = float(t_raw) if t_raw else 0.20
        except ValueError:
            price_gap_threshold = 0.20
        rescrape_env = os.getenv("PRICE_GAP_RESCRAPE", "true").strip().lower()
        rescrape_on = rescrape_env not in ("0", "false", "no", "off")
        soft_raw = os.getenv("MIN_MATCH_SCORE_SOFT_FLOOR", "").strip()
        try:
            soft_floor = float(soft_raw) if soft_raw else 42.0
        except ValueError:
            soft_floor = 42.0
        soft_floor = min(soft_floor, 47.9)  # must stay strictly below min_match_score default
        title_verify_env = os.getenv("LLM_TITLE_VERIFY", "true").strip().lower()
        title_verify_on = title_verify_env not in ("0", "false", "no", "off")
        price_verify_env = os.getenv("LLM_PRICE_VERIFY", "true").strip().lower()
        price_verify_on = price_verify_env not in ("0", "false", "no", "off")
        min_raw = os.getenv("PAGE_SETTLE_MIN_S", "").strip()
        max_raw = os.getenv("PAGE_SETTLE_MAX_S", "").strip()
        try:
            settle_min = float(min_raw) if min_raw else SETTLE_DELAY_MIN_S
        except ValueError:
            settle_min = SETTLE_DELAY_MIN_S
        try:
            settle_max = float(max_raw) if max_raw else SETTLE_DELAY_MAX_S
        except ValueError:
            settle_max = SETTLE_DELAY_MAX_S
        if settle_min > settle_max:
            settle_min, settle_max = settle_max, settle_min
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            firecrawl_api_key=firecrawl_key,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5.5"),
            price_gap_rescrape_threshold=price_gap_threshold,
            price_gap_rescrape_enabled=rescrape_on,
            llm_title_verify_enabled=title_verify_on,
            llm_price_verify_enabled=price_verify_on,
            min_match_score_soft_floor=soft_floor,
            settle_delay_min_s=settle_min,
            settle_delay_max_s=settle_max,
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
