#!/usr/bin/env bash
# Owner-run production restart for biap-global.service (port 8091).
# Usage: sudo deploy/restart-global-prod.sh <expected-commit-prefix>
# The service runs from this working tree, so "deploy" = verify tree + restart.
# Rollback: git checkout <previous-commit> (printed below) and rerun this script.
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
(cd analysis && PYTHONPATH=. .venv-global/bin/python -m pytest tests -q -x)
systemctl restart biap-global.service
for _ in $(seq 1 30); do
  sleep 2
  out="$(curl -fsS http://127.0.0.1:8091/health 2>/dev/null || true)"
  [[ "$out" == *"$head"* ]] && { echo "healthy: $out"; exit 0; }
done
echo "UNHEALTHY after restart; rollback: git checkout $prev && sudo $0 ${prev:0:7}" >&2
exit 1
