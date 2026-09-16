#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${BIAP_GLOBAL_DATA_DIR:-/var/lib/biap-global}"
SERVICE_USER="${BIAP_GLOBAL_SERVICE_USER:-ubuntu}"
SERVICE_GROUP="${BIAP_GLOBAL_SERVICE_GROUP:-$SERVICE_USER}"

as_root() {
  if [[ "$(id -u)" -eq 0 ]]; then "$@"; else sudo -n "$@"; fi
}

for path in \
  "$DATA_DIR/cache" \
  "$DATA_DIR/market" \
  "$DATA_DIR/source-index" \
  "$DATA_DIR/filings/US" \
  "$DATA_DIR/filings/EU" \
  "$DATA_DIR/filings/GB" \
  "$DATA_DIR/filings/NO" \
  "$DATA_DIR/filings/JP" \
  "$DATA_DIR/filings/AU" \
  "$DATA_DIR/filings/KR"; do
  as_root install -d -m 0750 -o "$SERVICE_USER" -g "$SERVICE_GROUP" "$path"
done

# Never make source evidence world-writable. Provider sync jobs should write
# atomically into these directories and retain source identifiers/URLs/hashes.
printf 'BIAP Global data directory ready: %s\n' "$DATA_DIR"
