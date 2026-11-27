#!/usr/bin/env bash
# Owner-run production restart for biap-global.service (port 8091).
# Usage: sudo deploy/restart-global-prod.sh <expected-commit-prefix>
# The service runs from this working tree, so "deploy" = verify tree + restart.
# Rollback: git checkout <previous-commit> (printed below) and rerun this script.
# Tests run as the sudo-invoking user (not root), see below.
set -euo pipefail
cd "$(dirname "$0")/.."
want="${1:?expected commit prefix}"
head="$(git rev-parse HEAD)"
[[ "$head" == "$want"* ]] || { echo "HEAD $head != $want" >&2; exit 1; }
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || { echo "dirty tree" >&2; exit 1; }
prev="$(curl -fsS http://127.0.0.1:8091/health | python3 -c 'import sys,json;print(json.load(sys.stdin)["commit"])')"
echo "previous live commit (rollback target): $prev"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
tar -C /var/lib/biap-global -czf "/var/backups/biap-global-fundamentals-$stamp.tgz" fundamentals scan-cache 2>/dev/null \
  && echo "backup: /var/backups/biap-global-fundamentals-$stamp.tgz" || echo "WARN: backup skipped"
# Tests run as the invoking (non-root) user with a raised open-files limit, an empty throw-away data directory and no bytecode/cache files,
# so the release leaves nothing owned by root in the tree or in /tmp and can never touch /var/lib/biap-global.
runas="${SUDO_USER:-}"
[[ -n "$runas" && "$runas" != "root" ]] || { echo "run this with sudo from a normal user (SUDO_USER is empty or root)" >&2; exit 1; }
ulimit -n 65536 2>/dev/null || ulimit -n "$(ulimit -Hn)"
echo "open-files limit for the tests: $(ulimit -n)"
testdata="$(mktemp -d /tmp/biap-release-tests.XXXXXX)"
trap 'rm -rf "$testdata"' EXIT
chown "$runas" "$testdata"
(cd analysis && runuser -u "$runas" -- env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 BIAP_GLOBAL_DATA_DIR="$testdata" \
   .venv-global/bin/python -m pytest tests -q -x -p no:cacheprovider)
systemctl restart biap-global.service
for _ in $(seq 1 30); do
  sleep 2
  out="$(curl -fsS http://127.0.0.1:8091/health 2>/dev/null || true)"
  [[ "$out" == *"$head"* ]] && { echo "healthy: $out"; exit 0; }
done
echo "UNHEALTHY after restart; rollback: git checkout $prev && sudo $0 ${prev:0:7}" >&2
exit 1
