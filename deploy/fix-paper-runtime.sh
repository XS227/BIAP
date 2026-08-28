#!/usr/bin/env bash
set -euo pipefail

REPO=/home/ubuntu/biap-kiasha/XS227-BIAP
RUNTIME_DIR=/etc/biap
RUNTIME_ENV=$RUNTIME_DIR/kiasha-paper-runtime.env
FIN_DROPIN_DIR=/etc/systemd/system/biap-fin.service.d
FIN_DROPIN=$FIN_DROPIN_DIR/zz-paper-runtime.conf
AUTO_SERVICE=/etc/systemd/system/biap-kiasha-auto-invest.service
AUTO_TIMER=/etc/systemd/system/biap-kiasha-auto-invest.timer

sudo install -d -m 0755 "$RUNTIME_DIR" "$FIN_DROPIN_DIR"

sudo tee "$RUNTIME_ENV" >/dev/null <<'EOF'
KIASHA_PAPER_EXECUTION_ENABLED=true
KIASHA_AUTO_INVEST_RUNNER_ENABLED=true
LIVE_TRADING_ENABLED=false
EOF
sudo chmod 0644 "$RUNTIME_ENV"

sudo tee "$FIN_DROPIN" >/dev/null <<EOF
[Service]
EnvironmentFile=$RUNTIME_ENV
EOF

sudo cp "$REPO/deploy/systemd/biap-kiasha-auto-invest.service" "$AUTO_SERVICE"
sudo cp "$REPO/deploy/systemd/biap-kiasha-auto-invest.timer" "$AUTO_TIMER"

sudo systemctl daemon-reload
sudo systemctl restart biap-fin
sudo systemctl enable --now biap-kiasha-auto-invest.timer

PID=$(systemctl show biap-fin -p MainPID --value)
printf 'biap-fin runtime flags:\n'
sudo sh -c "tr '\\0' '\\n' < /proc/$PID/environ | grep -E '^(KIASHA_PAPER_EXECUTION_ENABLED|KIASHA_AUTO_INVEST_RUNNER_ENABLED|LIVE_TRADING_ENABLED)='"
printf '\ntimer: '
systemctl is-active biap-kiasha-auto-invest.timer
printf 'fin: '
systemctl is-active biap-fin
