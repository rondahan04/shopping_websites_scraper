# QA Report: shopping_websites_scraper

| Field | Value |
|-------|-------|
| **Date** | 2026-05-15 |
| **URL** | `https://example.com` (Quick external smoke; repo has no first-party web UI) |
| **Branch** | main |
| **Commit** | bc67631 |
| **PR** | — |
| **Tier** | Standard (browser Quick + `scripts/verify-qa.sh`) |
| **Scope** | gstack `$B` browse after `npx playwright install chromium` in `~/.cursor/skills/gstack`. Project CLI unchanged; see `docs/QA.md` for local parity. |
| **Duration** | ~3 min (Playwright download + smoke + verify) |
| **Pages visited** | 1 |
| **Screenshots** | 1 (`screenshots/qa-example-initial.png`) |
| **Framework** | Static example page (smoke); app remains Python CLI |
| **Index** | — |

## Health Score: 96/100

Weighted rubric for the **visited page only** (example.com). Not a substitute for a real product URL.

| Category | Score |
|----------|-------|
| Console | 100 |
| Links | 100 |
| Visual | 100 |
| Functional | 100 |
| UX | 90 |
| Performance | 100 |
| Content | 90 |

Minor deductions: generic placeholder UX/content, not your shipped UI.

## Top 3 Things to Fix

1. **Local Python Playwright browsers** — If `verify-qa.sh` fails on Playwright launch, run `PLAYWRIGHT_BROWSERS_PATH=... .venv/bin/playwright install chromium` from `shopping_websites_scraper` (now green after install).
2. **gstack `$B` snapshot paths** — Browse only allows writes under `/private/tmp` or the gstack skill tree; copy artifacts into `.gstack/qa-reports/screenshots/` after capture.
3. **First-party URL** — When you ship a dashboard or preview host, pass it to `/gstack-qa` for meaningful coverage.

## Console Health

| Error | Count | First seen |
|-------|-------|--------------|
| (none) | 0 | https://example.com |

## Summary

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 0 |
| **Total** | **0** |

## Issues

_No product bugs filed from this run._

## Evidence

- **Navigate:** `https://example.com` (HTTP 200).
- **Annotated snapshot:** `.gstack/qa-reports/screenshots/qa-example-initial.png` (element `@e1` link “Learn more”).
- **`$B` links:** `Learn more` → `https://iana.org/domains/example`.

## Verification (project)

```bash
cd shopping_websites_scraper
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright-browsers"
bash scripts/verify-qa.sh
```

Result: **pytest 17 passed**; **Playwright (Python): Chromium launch OK**.

## Fixes Applied

| Issue | Fix Status | Commit | Files Changed |
|-------|-----------|--------|---------------|
| — | — | — | — |

(Environment only: Node Playwright for gstack installed under user cache; Python Chromium under `.playwright-browsers/`, gitignored.)

## PR Summary

> QA: gstack browse smoke on example.com (0 console errors); `verify-qa.sh` green (pytest 17 + Python Playwright launch).
