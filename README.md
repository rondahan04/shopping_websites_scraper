# Shopping Websites Scraper

Searches **Amazon**, **Best Buy**, **Walmart**, and **Newegg** for a product query, picks the best title match per site, and extracts price, rating, and review count (Scrapling → Playwright → LLM → Firecrawl fallback).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # OPENAI_API_KEY; optional FIRECRAWL_API_KEY
```

Uses **GPT-5.5** by default for LLM extraction (`OPENAI_MODEL` override supported).

## Usage

```bash
source .venv/bin/activate
python main.py "Lenovo Tab P12-2024"
# or
python main.py   # prompts for query
```

Output: `Website | Product title | Price | Average rating | Review count | Status | Method`

Exit code `0` if ≥3 sites succeed; `2` otherwise.

Optional: `--save-html ./html_debug` to dump SERP/product HTML locally (`html_debug/` is gitignored).

## Layout

- `main.py` — CLI
- `orchestrator.py` — parallel site runs
- `site_runner.py` — search → match → extract
- `sites/` — retailer adapters
- `extraction/` — fetch + fallback pipeline
- `matching/` — title similarity
- `validation/` — field checks
