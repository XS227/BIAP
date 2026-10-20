#!/bin/bash
# Cron entry point for research/daily_snapshot.py (low priority; address-space limit per exchange is set inside the script).
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$REPO/analysis" BIAP_GLOBAL_DATA_DIR="${BIAP_GLOBAL_DATA_DIR:-/var/lib/biap-global}" DECISION_MODE=investment
PY="${BIAP_SNAPSHOT_PYTHON:-/home/ubuntu/biap-global/BIAP/analysis/.venv-global/bin/python}"
mkdir -p "$BIAP_GLOBAL_DATA_DIR/logs"
exec nice -n 15 ionice -c3 "$PY" "$REPO/research/daily_snapshot.py" >> "$BIAP_GLOBAL_DATA_DIR/logs/daily-snapshot.log" 2>&1
