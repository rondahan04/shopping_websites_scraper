#!/usr/bin/env bash
# Run pytest + a minimal Playwright (Python) launch check.
# Does NOT install Node Playwright for gstack — see docs/QA.md
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$ROOT/.playwright-browsers}"

VENV_PY="$ROOT/.venv/bin/python"
VENV_PYTEST="$ROOT/.venv/bin/pytest"
if [[ ! -x "$VENV_PY" ]]; then
  echo "verify-qa: missing .venv — run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi

echo "==> pytest"
PYTHONPATH=. "$VENV_PYTEST" tests/ -q

echo "==> Playwright (Python) smoke launch"
"$VENV_PY" - <<'PY'
import os
import sys
from pathlib import Path

root = Path.cwd()
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(root / ".playwright-browsers"))

from playwright.sync_api import sync_playwright

try:
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True)
    browser.close()
    p.stop()
except Exception as e:
    print(
        "Playwright (Python): FAILED — from project root run:\n"
        "  source .venv/bin/activate && playwright install chromium",
        file=sys.stderr,
    )
    raise SystemExit(1) from e
print("Playwright (Python): Chromium launch OK")
PY

echo ""
echo "Optional (gstack browse / \$B):  npx playwright install"
echo "Docs: docs/QA.md"
