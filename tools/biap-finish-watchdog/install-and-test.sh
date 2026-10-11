#!/bin/bash
# Install, enable and test the BIAP finish-job watchdog. Run by the user: bash ~/biap-global/watchdog/install-and-test.sh
set -euo pipefail
WD=/home/ubuntu/biap-global/watchdog
chmod +x $WD/biap-finish-watchdog.sh
bash -n $WD/biap-finish-watchdog.sh
command -v jq >/dev/null || { echo "jq missing: sudo apt-get install -y jq"; exit 1; }

echo "== test 1: dry run, current clock (expect OK job running)"
WD_DRY_RUN=1 bash $WD/biap-finish-watchdog.sh
echo "== test 2: dry run, clock +60 min (expect WARN stalled + ACTION starting job attempt, nothing actually done)"
WD_DRY_RUN=1 WD_NOW_OFFSET_MIN=60 bash $WD/biap-finish-watchdog.sh
rm -f $WD/state/prompt-*.txt
echo "== test 3: lock (expect 'another watchdog run holds the lock')"
flock $WD/watchdog.lock -c "WD_DRY_RUN=1 bash $WD/biap-finish-watchdog.sh"

echo "== install units"
sudo install -m 644 $WD/biap-finish-watchdog.service $WD/biap-finish-watchdog.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now biap-finish-watchdog.timer
echo "== test 4: real run via systemd (job alive -> expect OK, no restart)"
sudo systemctl start biap-finish-watchdog.service
systemctl status biap-finish-watchdog.service --no-pager | tail -5
systemctl list-timers biap-finish-watchdog.timer --no-pager
systemctl is-enabled biap-finish-watchdog.timer
tmux ls
tail -8 /home/ubuntu/biap-global/logs/biap-finish-watchdog.log
