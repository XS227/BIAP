#!/usr/bin/env bash
# Rolls the gate-flag deploy back to the commit/page/env that were live just before it. Web service only.
set -euo pipefail
BK=${1:-$(cat /home/ubuntu/biap_research/last_gateflag_backup.txt)}
OLD=$(cat "$BK/COMMIT"); OLDBRANCH=$(cat "$BK/BRANCH"); PROD=/home/ubuntu/biap-global/BIAP
cd "$PROD"
git checkout -q "$OLDBRANCH"                                   # the gate-flag commit stays on feat/investment-gate-flag
[ "$(git rev-parse HEAD)" = "$OLD" ] || git reset --hard "$OLD"
cp -a "$BK/env.global" analysis/.env.global
sudo cp "$BK/index.html" /var/www/biap-global-web/index.html
sudo systemctl restart biap-global.service
sleep 6; curl -fsS http://127.0.0.1:8091/health
