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

  # Keep the web version lightweight, but make the broader Android app obvious and directly downloadable.
  as_root python3 - "$WEB_ROOT/index.html" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
marker = 'id="biap-android-app-download"'
if marker not in text:
    needle = "  <main>"
    if needle not in text:
        raise SystemExit("Could not find <main> in BIAP Global web page")
    banner = r'''  <section id="biap-android-app-download" style="padding:18px 0 2px">
    <div class="wrap">
      <div style="border:1px solid #315ecf;background:linear-gradient(135deg,rgba(31,73,166,.30),rgba(16,23,37,.97));border-radius:18px;padding:20px;display:flex;gap:18px;align-items:center;justify-content:space-between;flex-wrap:wrap;box-shadow:0 18px 60px rgba(0,0,0,.20)">
        <div style="min-width:240px;flex:1">
          <div class="eyebrow">FULL ANDROID EXPERIENCE</div>
          <h2 style="margin:7px 0 7px;font-size:22px">Get the full BIAP Global app</h2>
          <p style="margin:0;color:#9aa7bb;font-size:12px;line-height:1.65;max-width:760px">The web version is intentionally lightweight. The Android app includes the broader BIAP experience with Home, Market, full Stock Analysis, Kiasha AI Agents, Portfolio Agent and the extended module layer.</p>
          <div style="margin-top:9px;color:#8291aa;font-size:10px">BIAP Global 0.3.5 · Android ARM64 · about 45 MB</div>
        </div>
        <div style="display:flex;gap:9px;flex-wrap:wrap">
          <a href="/global/download/BIAP-Global-latest-arm64.apk" download style="display:inline-flex;align-items:center;justify-content:center;border-radius:12px;padding:12px 17px;background:linear-gradient(135deg,#3d7cff,#2754d9);color:#fff;font-weight:900;font-size:12px;text-decoration:none">Download Android APK</a>
          <a href="/global/download/BIAP-Global-latest-arm64.apk.sha256" style="display:inline-flex;align-items:center;justify-content:center;border:1px solid #324057;border-radius:12px;padding:12px 14px;color:#dce5f5;font-weight:800;font-size:11px;text-decoration:none">SHA-256</a>
        </div>
      </div>
    </div>
  </section>
'''
    text = text.replace(needle, banner + "\n" + needle, 1)
    path.write_text(text, encoding="utf-8")
PY
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
echo "BIAP Global API active at /global-api/, web app at /global/, Android APK at /global/download/. Backup: $BACKUP"
