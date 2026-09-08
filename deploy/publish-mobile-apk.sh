#!/usr/bin/env bash
set -euo pipefail

APK_SOURCE="${1:-}"
APP_DIR="${2:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
CHANNEL="${3:-stable}"

if [[ -z "$APK_SOURCE" || ! -f "$APK_SOURCE" ]]; then
  echo "usage: $0 /path/to/biap.apk [app-dir] [stable|expo]" >&2
  exit 2
fi

case "$CHANNEL" in
  stable)
    BASENAME="biap-latest"
    LABEL="stable APK"
    ;;
  expo)
    BASENAME="biap-expo"
    LABEL="Expo/EAS APK"
    ;;
  *)
    echo "unsupported channel: $CHANNEL (expected stable or expo)" >&2
    exit 2
    ;;
esac

MANIFEST="$APP_DIR/analysis/mobile_release.json"
if [[ ! -f "$MANIFEST" ]]; then
  echo "release manifest missing: $MANIFEST" >&2
  exit 2
fi

VERSION="$(python3 - "$MANIFEST" <<'PY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as fh:
    value = json.load(fh).get('version')
if not value:
    raise SystemExit(2)
print(value)
PY
)"

RELEASE_DIR="$APP_DIR/.runtime/releases"
mkdir -p "$RELEASE_DIR"
TMP_APK="$RELEASE_DIR/.${BASENAME}.apk.tmp"
TMP_VERSION="$RELEASE_DIR/.${BASENAME}.version.tmp"

install -m 0644 "$APK_SOURCE" "$TMP_APK"
printf '%s\n' "$VERSION" > "$TMP_VERSION"
chmod 0644 "$TMP_VERSION"
mv -f "$TMP_APK" "$RELEASE_DIR/${BASENAME}.apk"
mv -f "$TMP_VERSION" "$RELEASE_DIR/${BASENAME}.version"

echo "Published BIAP $VERSION ($LABEL)"
ls -lh "$RELEASE_DIR/${BASENAME}.apk" "$RELEASE_DIR/${BASENAME}.version"
