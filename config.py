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
    min_match_score: float = 55.0
    ambiguity_delta: float = 5.0
    max_serp_results: int = 15
    llm_max_chars: int = 20_000
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.5"
    firecrawl_api_key: str | None = None
    firecrawl_api_url: str = "https://api.firecrawl.dev/v1/scrape"
    max_workers: int = 4

    @classmethod
    def from_env(cls) -> Settings:
        firecrawl_key = os.getenv("FIRECRAWL_API_KEY") or os.getenv("FIRECRAWL_APY_KEY")
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            firecrawl_api_key=firecrawl_key,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5.5"),
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
