#!/usr/bin/env bash
set -euo pipefail

REPO="$HOME/BIAP"
ANALYSIS="$REPO/analysis"
LOG="$ANALYSIS/kiasha.log"

cd "$REPO"

# Preserve any server-local edits before updating from GitHub.
if ! git diff --quiet || ! git diff --cached --quiet; then
  git stash push -u -m "auto-stash-before-data-server-deploy-$(date +%Y%m%d-%H%M%S)"
fi

git pull --ff-only

cd "$ANALYSIS"

if [ -f tests/test_market_data_identifiers.py ]; then
  ./.venv/bin/python -m pytest tests/test_market_data_identifiers.py -q
fi

pkill -f "uvicorn api_server:app.*8088" 2>/dev/null || true
sleep 1

nohup env \
  BIAP_CODAL_BASE="http://89.42.199.20:8090/codal-search" \
  BIAP_CODAL_WWW_BASE="http://89.42.199.20:8090/codal-www" \
  BIAP_CODAL_EXCEL_BASE="http://89.42.199.20:8090/codal-excel" \
  BIAP_TSETMC_API_BASE="http://89.42.199.20:8090/tsetmc-cdn/api" \
  ./.venv/bin/uvicorn api_server:app --host 127.0.0.1 --port 8088 \
  > "$LOG" 2>&1 &

sleep 3

curl -fsS http://127.0.0.1:8088/health | python3 -m json.tool

echo
printf 'Recommendation test (ارفع):\n'
curl -fsS 'http://127.0.0.1:8088/stock/recommendation/%D8%A7%D8%B1%D9%81%D8%B9' || true
printf '\n\nLog: %s\n' "$LOG"
