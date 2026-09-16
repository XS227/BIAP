#!/usr/bin/env bash
set -euo pipefail

NGINX_SITE="${BIAP_NGINX_SITE:-/etc/nginx/sites-available/biap-dadashi}"
NGINX_ENABLED="${BIAP_NGINX_ENABLED:-/etc/nginx/sites-enabled/biap-dadashi}"

as_root() {
  if [[ "$(id -u)" -eq 0 ]]; then "$@"; else sudo -n "$@"; fi
}

test -f "$NGINX_SITE" || { echo "Missing nginx site: $NGINX_SITE" >&2; exit 1; }
TMP="$(mktemp)"
BACKUP="${NGINX_SITE}.bak-global-$(date +%Y%m%d%H%M%S)"
as_root cp "$NGINX_SITE" "$BACKUP"
cp "$NGINX_SITE" "$TMP"
trap 'rm -f "$TMP"' EXIT

python3 - "$TMP" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
marker = "    # BIAP_GLOBAL_API_ROUTE\n"
if marker in text:
    raise SystemExit(0)
needle = "    location /api/ {"
pos = text.find(needle)
if pos < 0:
    raise SystemExit("Could not find existing /api/ location; refusing unsafe nginx edit")
block = '''    # BIAP_GLOBAL_API_ROUTE
    # Separate Global research service; trailing slash intentionally strips
    # /global-api/ before forwarding, so /global-api/global/status -> /global/status.
    location ^~ /global-api/ {
        proxy_pass http://127.0.0.1:8091/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 10s;
        proxy_read_timeout 120s;
    }

'''
text = text[:pos] + block + text[pos:]
path.write_text(text, encoding="utf-8")
PY

as_root install -m 0644 "$TMP" "$NGINX_SITE"
if [[ ! -L "$NGINX_ENABLED" || "$(readlink -f "$NGINX_ENABLED" 2>/dev/null || true)" != "$(readlink -f "$NGINX_SITE")" ]]; then
  as_root rm -f "$NGINX_ENABLED"
  as_root ln -s "$NGINX_SITE" "$NGINX_ENABLED"
fi
if ! as_root nginx -t; then
  as_root cp "$BACKUP" "$NGINX_SITE"
  as_root nginx -t
  exit 1
fi
as_root systemctl reload nginx
echo "BIAP Global route active at /global-api/. Backup: $BACKUP"
