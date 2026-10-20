#!/usr/bin/env bash
# ROLLBACK to the pre-investment state. Usage: rollback_investment.sh <backup-dir>
set -euo pipefail
BK=${1:?backup dir, e.g. /var/lib/biap-global/backup-pre-investment-<stamp>}
OLD=$(cat "$BK/COMMIT"); PROD=/home/ubuntu/biap-global/BIAP
pkill -f reanalyze_ten.py || true
cd "$PROD"
git branch "rollback-keep-$(date -u +%Y%m%dT%H%M%SZ)" HEAD            # keep the investment commits reachable
git reset --hard "$OLD"
cp -a "$BK/env.global" analysis/.env.global
sudo cp "$BK/index.html" /var/www/biap-global-web/index.html
# restore ledgers only if the re-analysis damaged them (they are overwritten in place): uncomment
# for f in "$BK"/ledgers/*.sqlite3; do rm -f /var/lib/biap-global/analysis-ledger/$(basename "$f")-wal /var/lib/biap-global/analysis-ledger/$(basename "$f")-shm; cp -a "$f" /var/lib/biap-global/analysis-ledger/; done
sudo systemctl restart biap-global.service
sleep 6; curl -fsS http://127.0.0.1:8091/health

# ---------------------------------------------------------------------------------------------
# ROLLBACK of the gate-flag deploy only (branch feat/investment-gate-flag) back to investment-mode v1.
# Separate script: ~/biap_research/rollback_gateflag.sh (restores the backup recorded in last_gateflag_backup.txt).
