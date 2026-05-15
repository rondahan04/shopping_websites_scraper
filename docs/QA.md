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
