#!/usr/bin/env bash
# Installs the versioned price-refresh runner (P2.4) into /usr/local. Run with sudo after reading it.
# Backs up the current runner first; rollback: cp the .bak-* file back over /usr/local/bin/biap-global-price-refresh.
set -euo pipefail
SRC="$(cd "$(dirname "$0")/price-refresh" && pwd)"
DST=/usr/local/bin/biap-global-price-refresh
DRV=/usr/local/lib/biap-global-price-refresh/market_driver.py
cmp -s "$SRC/market_driver.py" "$DRV" || { echo "driver differs from production; aborting"; exit 1; }
cp -a "$DST" "$DST.bak-$(date -u +%Y%m%dT%H%M%SZ)"
install -m 0755 -o root -g root "$SRC/biap-global-price-refresh" "$DST"
bash -n "$DST" && echo "installed; next EU run picks it up (timer unchanged)"
