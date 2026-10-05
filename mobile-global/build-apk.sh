#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v npx >/dev/null 2>&1; then
  echo "Node/npm is required." >&2
  exit 1
fi

npm ci
npx eas-cli build --platform android --profile preview --non-interactive
