#!/bin/bash
# Rule: every engine change is tested on a rehearsal copy before live.  Usage: deploy/rehearsal-copy.sh [dest]
# Copies the ledgers + their inputs (not cache/backups) and prints the env to run a candidate commit against the copy.
set -eu
SRC=${BIAP_GLOBAL_DATA_DIR:-/var/lib/biap-global}
R=${1:-$HOME/rehearsal-$(date -u +%Y%m%dT%H%M%SZ)}
mkdir -p "$R/data"
for d in analysis-ledger daily-snapshots filings fx market scan-cache sector-reference shares source-index universe fundamentals; do
  [ -d "$SRC/$d" ] && cp -a "$SRC/$d" "$R/data/"
done
echo "rehearsal copy: $R/data"
echo "run:  set -a; . <repo>/analysis/.env.global; set +a; BIAP_GLOBAL_DATA_DIR=$R/data PYTHONPATH=<candidate>/analysis <venv>/bin/python -m <module>"
