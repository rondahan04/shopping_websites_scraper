# Shopping Websites Scraper

Fault-tolerant e-commerce scraper that searches **Amazon**, **Best Buy**, **Walmart**, and **Newegg** for a product query, picks the best title match per site, and extracts price, rating, and review count using a 4-method fallback pipeline.

## Setup

```bash
cd shopping_websites_scraper
npm install              # Husky: blocks commits/pushes with API keys or .env files
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

Output columns: `Website | Product title | Price | Average rating | Review count | Status | Method`

Exit code `0` if ≥3 sites succeed; `2` otherwise.

## Tests

```bash
source .venv/bin/activate
PYTHONPATH=. pytest tests/ -q
```

## Extraction fallback (per site)

**Search page:** Scrapling → Playwright → LLM SERP parse → Firecrawl HTML

**Product page:**

1. **Scrapling** (`Fetcher`, TLS impersonation + stealth headers) + BeautifulSoup — no Scrapling browser in M1 so thread-pool workers stay compatible with Playwright M2  
2. **Playwright** (headless)  
3. **LLM** (OpenAI JSON parse from page text)  
4. **Firecrawl** API  

Validation requires **title + price** only; rating and review count are best-effort (`N/A` when missing).

## Project layout

- `main.py` — CLI entry  
- `orchestrator.py` — parallel site runs  
- `site_runner.py` — search → match → extract  
- `matching/` — RapidFuzz similarity scoring  
- `extraction/` — M1–M4 pipeline + search fetch  
- `sites/` — per-retailer adapters  
- `validation/` — field and bot-page checks  
- `tests/fixtures/` — HTML samples for parser tests  
