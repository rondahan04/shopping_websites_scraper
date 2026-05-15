#!/usr/bin/env bash
# Two canonical product queries for manual / gstack-style QA (no browser required).
# Usage (from repo root Assignment 3, or from shopping_websites_scraper):
#   bash shopping_websites_scraper/scripts/run-two-product-qa.sh
#
# Optional: pass --save-html to dump SERP/product HTML under .gstack/qa-reports/html-<slug>/

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

SAVE_HTML=0
if [[ "${1:-}" == "--save-html" ]]; then
  SAVE_HTML=1
fi

if [[ ! -d .venv ]]; then
  echo "Create .venv in shopping_websites_scraper first (see README.md)." >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

QUERIES=(
  "Apple 14-inch MacBook Pro with M5 chip chip with 10 core CPU and 10 core GPU, 16GB, 1TB SSD - Space Black"
  "Lenovo Tab P12-2024"
)

REPORT_DIR="$ROOT/.gstack/qa-reports"
mkdir -p "$REPORT_DIR"

ANY_FAIL=0
for q in "${QUERIES[@]}"; do
  slug=$(echo "$q" | LC_ALL=C tr -cs 'a-zA-Z0-9' '_' | cut -c1-72 | sed 's/_$//')
  echo ""
  echo "================================================================"
  echo "$q"
  echo "================================================================"
  set +o pipefail
  if [[ "$SAVE_HTML" -eq 1 ]]; then
    HTML_DIR="$REPORT_DIR/html-$slug"
    mkdir -p "$HTML_DIR"
    PYTHONPATH=. python main.py "$q" --save-html "$HTML_DIR" 2>&1 | tee "$REPORT_DIR/cli-run-${slug}.log"
  else
    PYTHONPATH=. python main.py "$q" 2>&1 | tee "$REPORT_DIR/cli-run-${slug}.log"
  fi
  _py_rc=${PIPESTATUS[0]}
  set -o pipefail
  if [[ "$_py_rc" -ne 0 ]]; then
    echo "main.py exited ${_py_rc} for query (log: cli-run-${slug}.log)" >&2
    ANY_FAIL=1
  fi
done

echo ""
echo "Logs under: $REPORT_DIR/cli-run-*.log"
[[ "$SAVE_HTML" -eq 1 ]] && echo "HTML under:    $REPORT_DIR/html-*/"
exit "$ANY_FAIL"
