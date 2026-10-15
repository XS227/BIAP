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
mkdir -p "$BIAP_GLOBAL_DATA_DIR/source-index" "$BIAP_GLOBAL_DATA_DIR/filings/JP" "$BIAP_GLOBAL_DATA_DIR/fundamentals"

# Keep the instrument catalogs for the main global exchanges warm. Individual
# market failures are isolated inside universe_sync and never erase a good cache.
if ! "$PY" -m global_markets.universe_sync; then
  echo "UNIVERSE_SYNC: no market refreshed this run; existing snapshots preserved" >&2
fi

# Refresh the actual connected exchanges from the complete ordinary-equity
# universe. This replaces the old hand-maintained famous-ticker warmer. The scan
# cache is the daily market artifact used by This Market and Global Top 10.
if ! "$PY" -m global_markets.global_scan_refresh; then
  echo "GLOBAL_SCAN_REFRESH: refresh degraded; existing complete scan caches preserved" >&2
fi

# Build an outage-safe baseline for US, ESEF/UKSEF Europe and Türkiye. The job
# uses only a bounded cross-market QA set; every other company is persisted on
# demand after its first analysis. Existing official snapshots are never erased
# by a failed refresh.
if ! "$PY" -m global_markets.official_cache_warm; then
  echo "OFFICIAL_CACHE_WARM: refresh degraded; existing snapshots preserved" >&2
fi

# ESMA FIRDS ISIN -> issuer-LEI index (EU regulator reference data). Identity
# resolution for every EU market uses it before any name matching; rebuilding
# here keeps the ~40 s download out of the request path.
if ! "$PY" -c "from global_markets.firds_lei_index import ensure_index; import sys; sys.exit(0 if ensure_index() else 1)"; then
  echo "FIRDS_LEI_INDEX: refresh failed; previous index kept" >&2
fi

# Sweden/Norway/France/Spain: pre-parse the issuers' official ESEF annual reports from the
# national OAMs (FI Börsinformation / Oslo Newsweb) for the whole universe.
# Parsed documents are cached permanently by OAM document id, so after the
# first pass this only re-reads OAM listings for new filings.
if ! "$PY" -m global_markets.oam_esef_warm; then
  echo "OAM_ESEF_WARM: refresh degraded; existing snapshots preserved" >&2
fi

# Brazil (CVM) and Japan (EDINET) syncs are intentionally not run: background
# processing is limited to the SE/NO/FR/IT/GB/US allowlist
# (analysis/global_markets/background_scope.py). Their existing indexes and
# caches are preserved untouched.

# ESEF/GLEIF are queried by verified LEI and cached by the API layer. The warm
# job above pre-populates a representative baseline and on-demand analysis grows
# the archive over time. UK Companies House is queried only when its API key is
# configured. Australia is intentionally not scraped here: an authorized/
# licensed ingestion job must populate the verified filing drop.
echo "Global source sync completed safely."
