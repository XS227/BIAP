#!/bin/bash
# Installs the daily ECB refresh timer. Touches only /var/lib/biap-global/fx/ecb-hist.json at run time; restarts no service.
# Run with sudo from a checkout: sudo bash deploy/install-fx-refresh-timer.sh
set -eu
here="$(cd "$(dirname "$0")" && pwd)"
install -m 644 "$here/systemd/biap-global-fx-refresh.service" /etc/systemd/system/
install -m 644 "$here/systemd/biap-global-fx-refresh.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now biap-global-fx-refresh.timer
systemctl list-timers biap-global-fx-refresh.timer --no-pager
