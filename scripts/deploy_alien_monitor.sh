#!/usr/bin/env bash
# Build Alien Monitor, start Docker, wire nginx /monitor/ on magic-ai-factory.com.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MONITOR="$ROOT/alien-monitor"
NGINX_SITE="${NGINX_SITE:-/etc/nginx/sites-enabled/magic-ai-factory.com}"
SNIPPET="$ROOT/deploy/nginx/snippets/alien-monitor.conf"
PUBLIC_URL="${ALIEN_MONITOR_PUBLIC_URL:-https://magic-ai-factory.com/monitor/}"

echo "=== Alien Monitor deploy ==="

if [[ ! -d "$MONITOR" ]]; then
  echo "ERROR: $MONITOR not found" >&2
  exit 1
fi

# Stop dev processes that may hold :9100 / :5173
for port in 9100 5173; do
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" 2>/dev/null || true
  fi
done
sleep 1

cd "$MONITOR"
docker compose -f docker-compose.prod.yml up -d --build

echo "Waiting for health..."
for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:9100/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
curl -sf "http://127.0.0.1:9100/api/health" | head -c 200 || {
  echo "ERROR: Alien Monitor backend not healthy on :9100" >&2
  docker compose -f docker-compose.prod.yml logs --tail=40
  exit 1
}
echo ""

if [[ -f "$NGINX_SITE" ]] && [[ -f "$SNIPPET" ]]; then
  if grep -q 'location \^~ /monitor/' "$NGINX_SITE"; then
    echo "nginx: /monitor/ already configured in $NGINX_SITE"
  else
  echo "Patching nginx ($NGINX_SITE)..."
  python3 - "$NGINX_SITE" "$SNIPPET" <<'PY'
import sys
from pathlib import Path

site = Path(sys.argv[1])
snippet = Path(sys.argv[2]).read_text(encoding="utf-8")
text = site.read_text(encoding="utf-8")
marker = "    location / {"
if marker not in text:
    raise SystemExit(f"Could not find insertion point in {site}")
if "location ^~ /monitor/" in text:
    raise SystemExit(0)
site.write_text(text.replace(marker, snippet + "\n" + marker, 1), encoding="utf-8")
print(f"Patched {site}")
PY
  fi
  if command -v nginx >/dev/null 2>&1; then
    sudo nginx -t
    sudo systemctl reload nginx
  fi
else
  echo "NOTE: nginx site not found ($NGINX_SITE) — add deploy/nginx/snippets/alien-monitor.conf manually"
fi

echo ""
echo "Alien Monitor live at: $PUBLIC_URL"
echo "Health: ${PUBLIC_URL}api/health"
