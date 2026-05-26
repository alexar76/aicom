#!/usr/bin/env bash
# Build Alien Monitor + Pulse Terminal, start Docker, wire nginx /monitor/ and /pulse/.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MONITOR="$ROOT/alien-monitor"
NGINX_SITE="${NGINX_SITE:-/etc/nginx/sites-enabled/magic-ai-factory.com}"
SNIPPET_MONITOR="$ROOT/deploy/nginx/snippets/alien-monitor.conf"
SNIPPET_PULSE="$ROOT/deploy/nginx/snippets/pulse-terminal.conf"
PUBLIC_MONITOR="${ALIEN_MONITOR_PUBLIC_URL:-https://magic-ai-factory.com/monitor/}"
PUBLIC_PULSE="${PULSE_TERMINAL_PUBLIC_URL:-https://magic-ai-factory.com/pulse/}"

echo "=== Alien Monitor + Pulse Terminal deploy ==="

if [[ ! -d "$MONITOR" ]]; then
  echo "ERROR: $MONITOR not found" >&2
  exit 1
fi

# Stop dev processes that may hold demo ports
for port in 9100 5173 5199; do
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
  docker compose -f docker-compose.prod.yml logs --tail=40 alien-monitor
  exit 1
}
echo ""

echo "Waiting for Pulse Terminal on :5199..."
for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:5199/" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
curl -sf "http://127.0.0.1:5199/" -o /dev/null || {
  echo "ERROR: Pulse Terminal not serving on :5199" >&2
  docker compose -f docker-compose.prod.yml logs --tail=40 pulse-terminal
  exit 1
}
if curl -sf "http://127.0.0.1:9081/api/v2/capital/pricing?limit=1" >/dev/null 2>&1; then
  echo "Factory capital pricing API: OK"
else
  echo "WARNING: Factory GET /api/v2/capital/pricing not reachable on :9081"
fi
echo ""

patch_nginx_snippet() {
  local needle="$1"
  local snippet_path="$2"
  if [[ ! -f "$NGINX_SITE" ]] || [[ ! -f "$snippet_path" ]]; then
    return 1
  fi
  if grep -q "$needle" "$NGINX_SITE"; then
    echo "nginx: $needle already configured in $NGINX_SITE"
    return 0
  fi
  echo "Patching nginx ($NGINX_SITE) — $needle..."
  python3 - "$NGINX_SITE" "$snippet_path" "$needle" <<'PY'
import sys
from pathlib import Path

site = Path(sys.argv[1])
snippet = Path(sys.argv[2]).read_text(encoding="utf-8")
needle = sys.argv[3]
text = site.read_text(encoding="utf-8")
marker = "    location / {"
if marker not in text:
    raise SystemExit(f"Could not find insertion point in {site}")
if needle in text:
    raise SystemExit(0)
site.write_text(text.replace(marker, snippet + "\n" + marker, 1), encoding="utf-8")
print(f"Patched {site}")
PY
}

if [[ -f "$NGINX_SITE" ]]; then
  patch_nginx_snippet 'location ^~ /monitor/' "$SNIPPET_MONITOR" || true
  patch_nginx_snippet 'location ^~ /pulse/' "$SNIPPET_PULSE" || true
else
  echo "NOTE: nginx site not found ($NGINX_SITE) — add snippets under deploy/nginx/snippets/ manually"
fi

if command -v nginx >/dev/null 2>&1 && [[ -f "$NGINX_SITE" ]]; then
  sudo nginx -t
  sudo systemctl reload nginx
fi

echo ""
echo "Alien Monitor: $PUBLIC_MONITOR"
echo "Pulse Terminal: $PUBLIC_PULSE"
echo "Monitor health: ${PUBLIC_MONITOR}api/health"
