#!/usr/bin/env bash
# Decide whether a push/workflow_run on main needs the Kiasha/Iran VPS backend deploy.
# Global-only (and docs/research/CI-only) changes never trigger it. Usage: deploy-scope.sh <event> <sha> [before-sha]
# Prints "deploy=true|false", the reason and the changed files. Fail-safe: if the diff cannot be computed -> deploy=false.
set -uo pipefail
event="${1:?event}"; sha="${2:?sha}"; before="${3:-}"
SAFE_PATTERNS=(
  'analysis/global_markets/*'
  'analysis/global_*.py'
  'analysis/global_mobile_release.json'
  'analysis/.env.global.example'
  'analysis/tests/*'
  'mobile-global/*'
  'docs/*'
  'research/*'
  'tools/*'
  'STATUS_*.md'
  '*.md'
  'deploy/price-refresh/*'
  'deploy/systemd/biap-global*'
  'deploy/install-fx-refresh-timer.sh'
  'deploy/install-price-refresh-runner.sh'
  'deploy/deploy-scope.sh'
  '.github/workflows/deploy-backend.yml'
  # research / Global-only workflows (never touch the Kiasha/Iran VPS backend)
  '.github/workflows/biap-global-*.yml'
  '.github/workflows/biap-nov19-*.yml'
  '.github/workflows/biap-preliminary-*.yml'
  '.github/workflows/paper-portfolio-*.yml'
  '.github/workflows/research-*.yml'
)
if [[ "$event" == "workflow_dispatch" ]]; then echo "deploy=true"; echo "reason=manual dispatch"; exit 0; fi
zeros="0000000000000000000000000000000000000000"
if [[ "$event" == "push" && -n "$before" && "$before" != "$zeros" ]] && git cat-file -e "$before^{commit}" 2>/dev/null; then
  base="$before"
else
  base="$(git rev-parse --verify -q "$sha^1" || true)"
fi
if [[ -z "$base" ]]; then echo "deploy=false"; echo "reason=cannot determine base commit (fail-safe: no deploy)"; exit 0; fi
if ! changed="$(git diff --name-only "$base" "$sha")"; then echo "deploy=false"; echo "reason=git diff failed (fail-safe: no deploy)"; exit 0; fi
if [[ -z "$changed" ]]; then echo "deploy=false"; echo "reason=no changed files"; exit 0; fi
needs=()
while IFS= read -r f; do
  ok=0
  for pat in "${SAFE_PATTERNS[@]}"; do
    # shellcheck disable=SC2254
    case "$f" in $pat) ok=1; break;; esac
  done
  [[ $ok -eq 0 ]] && needs+=("$f")
done <<< "$changed"
if [[ ${#needs[@]} -gt 0 ]]; then
  echo "deploy=true"; echo "reason=deploy-relevant files changed"; printf 'file=%s\n' "${needs[@]:0:20}"
else
  echo "deploy=false"; echo "reason=only Global/docs/research/tests/CI files changed ($(wc -l <<< "$changed") files)"
fi
