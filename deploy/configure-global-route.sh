#!/usr/bin/env bash
set -euo pipefail

NGINX_SITE="${BIAP_NGINX_SITE:-/etc/nginx/sites-available/biap-dadashi}"
NGINX_ENABLED="${BIAP_NGINX_ENABLED:-/etc/nginx/sites-enabled/biap-dadashi}"
WEB_ROOT="${BIAP_GLOBAL_WEB_ROOT:-/var/www/biap-global-web}"
WEB_SOURCE="${BIAP_GLOBAL_WEB_SOURCE:-web-showcase/global/index.html}"
GLOBAL_HOST="${BIAP_GLOBAL_HOST:-global.biap.dadashi.no}"
GLOBAL_SITE="${BIAP_GLOBAL_NGINX_SITE:-/etc/nginx/sites-available/biap-global-subdomain}"
GLOBAL_ENABLED="${BIAP_GLOBAL_NGINX_ENABLED:-/etc/nginx/sites-enabled/biap-global-subdomain}"

as_root() {
  if [[ "$(id -u)" -eq 0 ]]; then "$@"; else sudo -n "$@"; fi
}

test -f "$NGINX_SITE" || { echo "Missing nginx site: $NGINX_SITE" >&2; exit 1; }
if [[ -f "$WEB_SOURCE" ]]; then
  as_root install -d -m 0755 "$WEB_ROOT"
  as_root install -d -m 0755 "$WEB_ROOT/download"
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

# ---------------------------------------------------------------------------
# Dedicated global.biap.dadashi.no virtual host.
# This is deliberately a separate origin so an old BIAP service worker/cache on
# biap.dadashi.no cannot intercept or replace the Global application.
# ---------------------------------------------------------------------------
GLOBAL_HTTP_TMP="$(mktemp)"
cat > "$GLOBAL_HTTP_TMP" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${GLOBAL_HOST};

    root ${WEB_ROOT};
    index index.html;

    location ^~ /.well-known/acme-challenge/ {
        root ${WEB_ROOT};
        try_files \$uri =404;
    }

    location ^~ /global-api/ {
        proxy_pass http://127.0.0.1:8091/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 10s;
        proxy_read_timeout 120s;
    }

    # Both paths are supported so APK links remain valid before/after migration.
    location ^~ /download/ {
        alias ${WEB_ROOT}/download/;
        try_files \$uri =404;
    }
    location ^~ /global/download/ {
        alias ${WEB_ROOT}/download/;
        rewrite ^/global/download/(.*)$ /download/\$1 last;
    }

    location = /global { return 302 /; }
    location = /global/ { return 302 /; }

    location / {
        try_files \$uri \$uri/ /index.html;
        add_header Cache-Control "no-store, no-cache, must-revalidate" always;
        add_header Pragma "no-cache" always;
        add_header Expires "0" always;
    }
}
EOF
as_root install -m 0644 "$GLOBAL_HTTP_TMP" "$GLOBAL_SITE"
rm -f "$GLOBAL_HTTP_TMP"
if [[ ! -L "$GLOBAL_ENABLED" || "$(readlink -f "$GLOBAL_ENABLED" 2>/dev/null || true)" != "$(readlink -f "$GLOBAL_SITE")" ]]; then
  as_root rm -f "$GLOBAL_ENABLED"
  as_root ln -s "$GLOBAL_SITE" "$GLOBAL_ENABLED"
fi

# First validate/reload the HTTP vhost. It is safe even before DNS exists.
as_root nginx -t
as_root systemctl reload nginx

# Check whether the new hostname resolves to this VPS. Only then attempt ACME.
DNS_READY=0
ORIGIN_IP="$(curl -4fsS --max-time 8 https://api.ipify.org 2>/dev/null || true)"
if [[ -n "$ORIGIN_IP" ]]; then
  while read -r resolved; do
    if [[ "$resolved" == "$ORIGIN_IP" ]]; then DNS_READY=1; break; fi
  done < <(getent ahostsv4 "$GLOBAL_HOST" 2>/dev/null | awk '{print $1}' | sort -u)
fi

# Reuse any existing certificate that already covers the hostname.
CERT_FULLCHAIN=""
CERT_PRIVKEY=""
if [[ -d /etc/letsencrypt/live ]]; then
  while IFS= read -r cert; do
    if as_root openssl x509 -in "$cert" -noout -checkhost "$GLOBAL_HOST" >/dev/null 2>&1; then
      candidate_dir="$(dirname "$cert")"
      if [[ -f "$candidate_dir/privkey.pem" ]]; then
        CERT_FULLCHAIN="$cert"
        CERT_PRIVKEY="$candidate_dir/privkey.pem"
        break
      fi
    fi
  done < <(as_root find /etc/letsencrypt/live -mindepth 2 -maxdepth 2 -name fullchain.pem -type l 2>/dev/null || true)
fi

# If DNS is live but no covering cert exists, obtain one non-interactively when
# certbot is already available on the VPS. No certificate request is made until
# DNS definitely points to this machine.
if [[ "$DNS_READY" -eq 1 && -z "$CERT_FULLCHAIN" ]] && command -v certbot >/dev/null 2>&1; then
  as_root certbot certonly --webroot -w "$WEB_ROOT" -d "$GLOBAL_HOST" \
    --non-interactive --agree-tos --register-unsafely-without-email || true
  if [[ -f "/etc/letsencrypt/live/${GLOBAL_HOST}/fullchain.pem" && -f "/etc/letsencrypt/live/${GLOBAL_HOST}/privkey.pem" ]]; then
    CERT_FULLCHAIN="/etc/letsencrypt/live/${GLOBAL_HOST}/fullchain.pem"
    CERT_PRIVKEY="/etc/letsencrypt/live/${GLOBAL_HOST}/privkey.pem"
  fi
fi

SUBDOMAIN_READY=0
if [[ "$DNS_READY" -eq 1 && -n "$CERT_FULLCHAIN" && -n "$CERT_PRIVKEY" ]]; then
  GLOBAL_TLS_TMP="$(mktemp)"
  cat > "$GLOBAL_TLS_TMP" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${GLOBAL_HOST};
    location ^~ /.well-known/acme-challenge/ { root ${WEB_ROOT}; try_files \$uri =404; }
    location / { return 308 https://${GLOBAL_HOST}\$request_uri; }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ${GLOBAL_HOST};

    ssl_certificate ${CERT_FULLCHAIN};
    ssl_certificate_key ${CERT_PRIVKEY};

    root ${WEB_ROOT};
    index index.html;

    location ^~ /global-api/ {
        proxy_pass http://127.0.0.1:8091/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 10s;
        proxy_read_timeout 120s;
    }

    location ^~ /download/ {
        alias ${WEB_ROOT}/download/;
        try_files \$uri =404;
    }
    location ^~ /global/download/ {
        rewrite ^/global/download/(.*)$ /download/\$1 permanent;
    }

    location = /global { return 308 /; }
    location = /global/ { return 308 /; }

    location / {
        try_files \$uri \$uri/ /index.html;
        add_header Cache-Control "no-store, no-cache, must-revalidate" always;
        add_header Pragma "no-cache" always;
        add_header Expires "0" always;
    }
}
EOF
  as_root install -m 0644 "$GLOBAL_TLS_TMP" "$GLOBAL_SITE"
  rm -f "$GLOBAL_TLS_TMP"
  as_root nginx -t
  as_root systemctl reload nginx
  SUBDOMAIN_READY=1
fi

# ---------------------------------------------------------------------------
# Legacy biap.dadashi.no/global/ route.
# It remains available until the isolated hostname is confirmed with both DNS
# and TLS. Once confirmed, fresh requests are redirected to the new origin.
# ---------------------------------------------------------------------------
TMP="$(mktemp)"
BACKUP="${NGINX_SITE}.bak-global-$(date +%Y%m%d%H%M%S)"
as_root cp "$NGINX_SITE" "$BACKUP"
cp "$NGINX_SITE" "$TMP"
trap 'rm -f "$TMP"' EXIT

python3 - "$TMP" "$WEB_ROOT" "$GLOBAL_HOST" "$SUBDOMAIN_READY" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
web_root = str(sys.argv[2]).rstrip("/")
global_host = str(sys.argv[3]).strip()
redirect_ready = str(sys.argv[4]) == "1"
if not web_root.startswith("/") or any(ch in web_root for ch in "\n\r;{}"):
    raise SystemExit("Unsafe BIAP_GLOBAL_WEB_ROOT; refusing nginx edit")
if not re.fullmatch(r"[a-z0-9.-]+", global_host):
    raise SystemExit("Unsafe BIAP_GLOBAL_HOST; refusing nginx edit")

text = path.read_text(encoding="utf-8")
api_marker = "    # BIAP_GLOBAL_API_ROUTE\n"
web_marker = "    # BIAP_GLOBAL_WEB_ROUTE\n"
needle = "    location /api/ {"
pos = text.find(needle)
if pos < 0:
    raise SystemExit("Could not find existing /api/ location; refusing unsafe nginx edit")

if redirect_ready:
    web_block = f'''    # BIAP_GLOBAL_WEB_ROUTE
    location = /global {{
        return 308 https://{global_host}/;
    }}

    location ^~ /global/ {{
        rewrite ^/global/(.*)$ https://{global_host}/$1 permanent;
    }}

'''
else:
    web_block = f'''    # BIAP_GLOBAL_WEB_ROUTE
    location = /global {{
        return 301 /global/;
    }}

    location ^~ /global/ {{
        alias {web_root}/;
        index index.html;
        try_files $uri $uri/ =404;
        add_header Cache-Control "no-cache";
    }}

'''

# Replace the previously managed web block if present; otherwise insert it.
if web_marker in text:
    start = text.index(web_marker)
    end_candidates = [i for i in (text.find(api_marker, start + len(web_marker)), text.find(needle, start + len(web_marker))) if i >= 0]
    if not end_candidates:
        raise SystemExit("Could not find end of managed Global web block")
    end = min(end_candidates)
    text = text[:start] + web_block + text[end:]
else:
    text = text[:pos] + web_block + text[pos:]

if api_marker not in text:
    pos = text.find(needle)
    api_block = '''    # BIAP_GLOBAL_API_ROUTE
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
    text = text[:pos] + api_block + text[pos:]

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

if [[ "$SUBDOMAIN_READY" -eq 1 ]]; then
  echo "BIAP Global isolated origin active at https://${GLOBAL_HOST}/; legacy /global/ now redirects. Backup: $BACKUP"
elif [[ "$DNS_READY" -eq 1 ]]; then
  echo "BIAP Global subdomain DNS reaches this VPS, but a covering TLS certificate is not ready yet. Legacy /global/ remains active."
else
  echo "BIAP Global subdomain vhost is prepared for ${GLOBAL_HOST}, but DNS does not yet resolve to this VPS (${ORIGIN_IP:-unknown}). Legacy /global/ remains active."
fi
