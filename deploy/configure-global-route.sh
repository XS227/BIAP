#!/usr/bin/env bash
set -euo pipefail

NGINX_SITE="${BIAP_NGINX_SITE:-/etc/nginx/sites-available/biap-dadashi}"
NGINX_ENABLED="${BIAP_NGINX_ENABLED:-/etc/nginx/sites-enabled/biap-dadashi}"
WEB_ROOT="${BIAP_GLOBAL_WEB_ROOT:-/var/www/biap-global-web}"
WEB_SOURCE="${BIAP_GLOBAL_WEB_SOURCE:-web-showcase/global/index.html}"

as_root() {
  if [[ "$(id -u)" -eq 0 ]]; then "$@"; else sudo -n "$@"; fi
}

test -f "$NGINX_SITE" || { echo "Missing nginx site: $NGINX_SITE" >&2; exit 1; }
if [[ -f "$WEB_SOURCE" ]]; then
  as_root install -d -m 0755 "$WEB_ROOT"
  as_root install -m 0644 "$WEB_SOURCE" "$WEB_ROOT/index.html"
else
  echo "Warning: BIAP Global web source not found at $WEB_SOURCE; keeping API route deployment." >&2
fi

TMP="$(mktemp)"
BACKUP="${NGINX_SITE}.bak-global-$(date +%Y%m%d%H%M%S)"
as_root cp "$NGINX_SITE" "$BACKUP"
cp "$NGINX_SITE" "$TMP"
trap 'rm -f "$TMP"' EXIT

python3 - "$TMP" "$WEB_ROOT" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
web_root = str(sys.argv[2]).rstrip("/")
if not web_root.startswith("/") or any(ch in web_root for ch in "\n\r;{}"):
    raise SystemExit("Unsafe BIAP_GLOBAL_WEB_ROOT; refusing nginx edit")

text = path.read_text(encoding="utf-8")
api_marker = "    # BIAP_GLOBAL_API_ROUTE\n"
web_marker = "    # BIAP_GLOBAL_WEB_ROUTE\n"
needle = "    location /api/ {"
pos = text.find(needle)
if pos < 0:
    raise SystemExit("Could not find existing /api/ location; refusing unsafe nginx edit")

blocks = []
if web_marker not in text:
    blocks.append(f'''    # BIAP_GLOBAL_WEB_ROUTE
    location = /global {{
        return 301 /global/;
    }}

    location ^~ /global/ {{
        alias {web_root}/;
        index index.html;
        try_files $uri $uri/ =404;
        add_header Cache-Control "no-cache";
    }}

''')

if api_marker not in text:
    blocks.append('''    # BIAP_GLOBAL_API_ROUTE
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

''')

if blocks:
    text = text[:pos] + "".join(blocks) + text[pos:]
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
echo "BIAP Global API active at /global-api/ and web app at /global/. Backup: $BACKUP"
