# QA & verification

This project is a **Python CLI** (`python main.py "query"`). There is no first-party HTTP server or SPA, so **gstack browse**-style browser rubrics (console, links, visual, …) do not apply unless you add a UI later.

## Primary verification (always run)

```bash
cd shopping_websites_scraper
source .venv/bin/activate
PYTHONPATH=. pytest tests/ -q
```

Or the bundled script (uses `.venv` directly):

```bash
cd shopping_websites_scraper
npm run qa:verify
# or: bash scripts/verify-qa.sh
```

## Two different Playwright installations

| Context | Install command | Purpose |
|--------|------------------|---------|
| **This scraper (Python M2)** | From activated venv: `playwright install chromium` | Headless fetch in `extraction/playwright_extract.py` |
| **gstack browse / `$B`** | `npx playwright install` or `bun x playwright install` | Separate Node/browser bundle used by gstack skills |

Installing only one does **not** satisfy the other. If `main.py` says the browser is missing, fix the **Python** install. If gstack QA reports `chrome-headless-shell` missing, fix the **Node** install.

## gstack browse / `$B` prerequisites

1. Install browsers for the tool gstack uses (often Node Playwright):

   ```bash
   npx playwright install
   ```

   If your setup uses **bun**, ensure it is on `PATH` before invoking `$B`:

   ```bash
   export PATH="$HOME/.bun/bin:$PATH"
   ```

   Add that line to `~/.zshrc` or `~/.bashrc` if scripts invoke gstack without a login shell.

   Optional helper (prepends `~/.bun/bin` to `PATH`):

   ```bash
   source shopping_websites_scraper/scripts/gstack-browse-env.sh
   ```

2. Re-run gstack QA with a **target URL** only when you have something to browse (e.g. a future dashboard). Until then, treat **pytest + manual CLI runs** as the source of truth.

## Manual CLI checks

```bash
source .venv/bin/activate
python main.py "Lenovo Tab P12-2024"
```

Save HTML for parser debugging:

```bash
python main.py "Lenovo Tab P12" --save-html ./html_debug
```

See `README.md` for exit codes and columns.

## Staging URL (when you add a UI)

Set a stable URL for human or browse-based QA, e.g. in `.env`:

```bash
QA_STAGING_URL=http://127.0.0.1:8080
```

Document the actual URL and how to start the server in this file when the UI exists.

## `/gstack-qa` and this CLI (two product queries)

**`/gstack-qa`** is built for **browsing a URL** (SPA, dashboard). This repo has **no** first-party URL to open, so gstack cannot “click through” your scraper.

To QA **two real products** the same way you would prove the scraper works in a report:

### Option A — one command (recommended)

From **`shopping_websites_scraper`** (venv + `pip install` + `playwright install chromium` already done):

```bash
bash scripts/run-two-product-qa.sh
```

With HTML dumps for debugging parsers:

```bash
bash scripts/run-two-product-qa.sh --save-html
```

That runs `main.py` for:

1. Apple 14-inch MacBook Pro (M5, 16GB, 1TB, Space Black) — *note: duplicate “chip” in the string matches your original wording; edit the script if you want a shorter query.*
2. Lenovo Tab P12-2024

Logs go to **`.gstack/qa-reports/cli-run-*.log`** (under the scraper project). With `--save-html`, HTML goes under **`.gstack/qa-reports/html-*`**.

### Option B — tell the agent running `/gstack-qa`

Paste something like:

> This repo is CLI-only. Do **not** use browse for the app surface. Run from `shopping_websites_scraper`: `npm run qa:verify`, then `bash scripts/run-two-product-qa.sh` (add `--save-html` if you need HTML). Summarize success/fail per retailer in `.gstack/qa-reports/`.

### Option C — manual one-liners

```bash
cd shopping_websites_scraper && source .venv/bin/activate
PYTHONPATH=. python main.py 'Apple 14-inch MacBook Pro with M5 chip chip with 10 core CPU and 10 core GPU, 16GB, 1TB SSD - Space Black'
PYTHONPATH=. python main.py 'Lenovo Tab P12-2024'
```

## Price-gap rescrape

After the first multi-site run, `main.py` compares **successful** prices to their **mean**. Any site more than **30%** away (relative to the mean) is **rescraped once** with the same search query.

- **CLI:** `python main.py "query"` — add `--no-price-gap-rescrape` to skip.
- **Env:** `PRICE_GAP_RESCRAPE_THRESHOLD` (default `0.30`), `PRICE_GAP_MIN_PRICED_SITES` (default `2`, minimum at least 2), `PRICE_GAP_RESCRAPE=false` to disable.

Requires at least two priced successes to compute a mean; failed or `N/A` rows are excluded from the mean but are not rescraped by this pass.
