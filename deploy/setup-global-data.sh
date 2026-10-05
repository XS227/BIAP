#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${BIAP_GLOBAL_DATA_DIR:-/var/lib/biap-global}"
SERVICE_USER="${BIAP_GLOBAL_SERVICE_USER:-ubuntu}"
SERVICE_GROUP="${BIAP_GLOBAL_SERVICE_GROUP:-$SERVICE_USER}"

as_root() {
  if [[ "$(id -u)" -eq 0 ]]; then "$@"; else sudo -n "$@"; fi
}

# The service writes persistent reference, market and filing snapshots below
# DATA_DIR. Own the root itself as well as every first-level writable cache
# directory; otherwise a sandboxed systemd service can have ReadWritePaths
# permission but still fail normal Unix directory traversal/creation with
# PermissionError.
as_root install -d -m 0750 -o "$SERVICE_USER" -g "$SERVICE_GROUP" "$DATA_DIR"

for path in \
  "$DATA_DIR/cache" \
  "$DATA_DIR/universe" \
  "$DATA_DIR/market" \
  "$DATA_DIR/source-index" \
  "$DATA_DIR/filings/US" \
  "$DATA_DIR/filings/EU" \
  "$DATA_DIR/filings/GB" \
  "$DATA_DIR/filings/DE" \
  "$DATA_DIR/filings/NO" \
  "$DATA_DIR/filings/SG" \
  "$DATA_DIR/filings/HK" \
  "$DATA_DIR/filings/JP" \
  "$DATA_DIR/filings/AU" \
  "$DATA_DIR/filings/KR"; do
  as_root install -d -m 0750 -o "$SERVICE_USER" -g "$SERVICE_GROUP" "$path"
done

# Never make source evidence world-writable. Provider sync jobs write atomically
# and retain source identifiers/URLs/hashes. Verify that the runtime identity can
# create an atomic universe-cache file before the service is restarted.
PROBE_DIR="$DATA_DIR/universe/.write-probe"
as_root install -d -m 0750 -o "$SERVICE_USER" -g "$SERVICE_GROUP" "$PROBE_DIR"
if [[ "$(id -un)" == "$SERVICE_USER" ]]; then
  printf 'ok\n' > "$PROBE_DIR/probe.tmp"
  mv "$PROBE_DIR/probe.tmp" "$PROBE_DIR/probe"
  rm -f "$PROBE_DIR/probe"
else
  as_root runuser -u "$SERVICE_USER" -- sh -c "printf 'ok\\n' > '$PROBE_DIR/probe.tmp' && mv '$PROBE_DIR/probe.tmp' '$PROBE_DIR/probe' && rm -f '$PROBE_DIR/probe'"
fi
as_root rmdir "$PROBE_DIR"

printf 'BIAP Global data directory ready and writable: %s\n' "$DATA_DIR"
