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
cp .env.example .env   # OPENAI_API_KEY; optional FIRECRAWL_API_KEY; optional QA_STAGING_URL (see docs/QA.md)
```

See **[docs/QA.md](docs/QA.md)** for gstack browse (Node Playwright + `bun` PATH), CI, and staging URL when you add a UI.

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

After the first parallel scrape, the CLI **compares successful prices** to their **arithmetic mean**. Any site whose price differs by **more than 30%** from that mean is **rescraped once** with the same query (fresh SERP + product pipeline). Disable with **`--no-price-gap-rescrape`**. Tune with env: `PRICE_GAP_RESCRAPE_THRESHOLD` (default `0.30`), `PRICE_GAP_MIN_PRICED_SITES` (default `2`), `PRICE_GAP_RESCRAPE=false` to turn off globally.

### Debug: save HTML

```bash
python main.py "Lenovo Tab P12" --save-html ./html_debug
```

Writes per-site `*_serp.html` (search page) and `*_product.html` (product page when available). See `docs/QA.md`.

## QA & CI

- **Full checklist:** [docs/QA.md](docs/QA.md) — pytest vs Playwright (Python) vs gstack browse (Node), `bun` on `PATH`, staging URL when you add a UI.
- **One-shot verify:** `npm run qa:verify` or `bash scripts/verify-qa.sh` (pytest + Chromium launch smoke test).
- **Two-product CLI smoke (MacBook + Lenovo Tab):** `bash scripts/run-two-product-qa.sh` — see [docs/QA.md § gstack-qa](docs/QA.md#gstack-qa-and-this-cli-two-product-queries); add `--save-html` for HTML dumps.

GitHub Actions runs the same tests and installs Chromium on push/PR under `shopping_websites_scraper/`.

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
