# Shopping Websites Scraper

Searches **Amazon**, **Best Buy**, **Walmart**, and **Newegg** for a product query, picks the best title match per site, and extracts price, rating, and review count (HTTP/httpx → Playwright → LLM → Firecrawl fallback). If no price is found, retries via a US proxy when `USA_HTTP_PROXY` is set.

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

## Web UI (FastAPI + Next.js)

Terminal 1 — API (port 8000):

```bash
source .venv/bin/activate
pip install -r requirements.txt
npm run api
```

Terminal 2 — UI (port 3000, proxies `/api/*` to the API):

```bash
npm run web:install   # once
npm run web
```

Open http://localhost:3000, enter a product query, and watch the progress bar while stores are checked (usually a few minutes).

API: `GET /health`, `POST /api/search/jobs` to start a search, then poll `GET /api/search/jobs/{job_id}` until `status` is `done` (avoids browser timeouts on long scrapes).

## Layout

- `main.py` — CLI
- `api/` — FastAPI HTTP layer
- `web/` — Next.js search UI
- `orchestrator.py` — parallel site runs
- `site_runner.py` — search → match → extract
- `sites/` — retailer adapters
- `extraction/` — fetch + fallback pipeline
- `matching/` — title similarity
- `validation/` — field checks
