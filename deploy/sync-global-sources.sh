#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${BIAP_GLOBAL_APP_DIR:-/home/ubuntu/biap-global/BIAP}"
ENV_FILE="${BIAP_GLOBAL_ENV_FILE:-$APP_DIR/analysis/.env.global}"
PY="$APP_DIR/analysis/.venv-global/bin/python"
export PYTHONPATH="$APP_DIR/analysis"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

export BIAP_GLOBAL_DATA_DIR="${BIAP_GLOBAL_DATA_DIR:-/var/lib/biap-global}"
mkdir -p "$BIAP_GLOBAL_DATA_DIR/source-index" "$BIAP_GLOBAL_DATA_DIR/filings/JP"

# Japan: keep a small rolling window current after the initial bootstrap.
if [[ -n "${BIAP_EDINET_API_KEY:-}" ]]; then
  "$PY" -m global_markets.edinet_sync --days "${BIAP_EDINET_DAILY_SYNC_DAYS:-4}"
else
  echo "EDINET: skipped (BIAP_EDINET_API_KEY not configured)"
fi

# ESEF/GLEIF are queried on demand by verified LEI and may be cached by the API
# layer. Australia is intentionally not scraped here: an authorized/licensed
# ingestion job must populate the verified filing drop.
echo "Global source sync completed safely."
