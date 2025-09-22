#!/usr/bin/env bash
set -euo pipefail
# Render deploy/nginx.conf with a domain and install to /etc/nginx/sites-available.
# Usage: sudo ./deploy/render_nginx.sh your.domain.tld

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Please run as root (sudo)" >&2
  exit 1
fi

DOMAIN="${1:-}"
if [[ -z "$DOMAIN" ]]; then
  echo "Usage: $0 your.domain.tld" >&2
  exit 1
fi

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
TPL="$SRC_DIR/nginx.conf"
DST="/etc/nginx/sites-available/quantum-commander.conf"

sed "s/{{YOUR_DOMAIN}}/$DOMAIN/g" "$TPL" > "$DST"
ln -sf "$DST" /etc/nginx/sites-enabled/quantum-commander.conf
nginx -t
systemctl reload nginx

echo "Installed Nginx config for $DOMAIN -> http://127.0.0.1:8000"