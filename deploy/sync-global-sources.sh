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

# Keep the instrument catalogs for the main global exchanges warm. Individual
# market failures are isolated inside universe_sync and never erase a good cache.
if ! "$PY" -m global_markets.universe_sync; then
  echo "UNIVERSE_SYNC: no market refreshed this run; existing snapshots preserved" >&2
fi

# Brazil: CVM DFP is regulator-published open data. It is updated weekly, so do
# not download the annual ZIPs every day; bootstrap immediately and refresh when
# the compact local index is older than six days. A failed refresh never deletes
# the last verified index.
CVM_INDEX="$BIAP_GLOBAL_DATA_DIR/source-index/cvm-dfp.json"
CVM_REFRESH=0
if [[ ! -s "$CVM_INDEX" ]]; then
  CVM_REFRESH=1
elif find "$CVM_INDEX" -mtime +6 -print -quit | grep -q .; then
  CVM_REFRESH=1
fi
if [[ "$CVM_REFRESH" -eq 1 ]]; then
  if ! "$PY" -m global_markets.cvm_sync; then
    echo "CVM: refresh failed; existing verified index preserved" >&2
  fi
else
  echo "CVM: recent verified DFP index already present"
fi

# Japan: keep a small rolling EDINET window current after the initial bootstrap.
if [[ -n "${BIAP_EDINET_API_KEY:-}" ]]; then
  "$PY" -m global_markets.edinet_sync --days "${BIAP_EDINET_DAILY_SYNC_DAYS:-4}"
else
  echo "EDINET: skipped (BIAP_EDINET_API_KEY not configured)"
fi

# ESEF/GLEIF are queried on demand by verified LEI and cached by the API layer.
# UK Companies House is queried only when its API key is configured. Australia
# is intentionally not scraped here: an authorized/licensed ingestion job must
# populate the verified filing drop for official fundamentals.
echo "Global source sync completed safely."
