#!/usr/bin/env bash
# Build and start ARGUS reference agent on 127.0.0.1:8787 (HTTP /health + /arena).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARGUS="$ROOT/argus"
ENV_FILE="$ARGUS/.env"
CONFIG_FILE="$ARGUS/argus.config.json"
NGINX_SITE="${NGINX_SITE:-/etc/nginx/sites-enabled/magic-ai-factory.com}"
SNIPPET_ARGUS="$ROOT/deploy/nginx/snippets/argus-arena.conf"
PUBLIC_ARGUS_URL="${ARGUS_PUBLIC_URL:-https://magic-ai-factory.com/arena}"
PUBLIC_ARGUS_ARENA="${PUBLIC_ARGUS_URL%/}"
if [[ "$PUBLIC_ARGUS_ARENA" != */arena ]]; then
  PUBLIC_ARGUS_ARENA="${PUBLIC_ARGUS_ARENA}/arena"
fi

echo "=== ARGUS deploy ==="

if [[ ! -d "$ARGUS" ]]; then
  echo "ERROR: $ARGUS not found" >&2
  exit 1
fi

if [[ ! -f "$CONFIG_FILE" ]]; then
  cp "$ARGUS/argus.config.example.json" "$CONFIG_FILE"
  echo "Created $CONFIG_FILE from example (edit for local providers/models)"
fi

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ARGUS/.env.example" "$ENV_FILE"
  echo "Created $ENV_FILE from example — add provider keys / Telegram token as needed"
fi

# Ensure HTTP port is set for compose + health probes.
python3 <<PY
from pathlib import Path

env_path = Path("$ENV_FILE")
lines = env_path.read_text(encoding="utf-8").splitlines()
out = []
has_port = False
for ln in lines:
    if ln.startswith("ARGUS_HTTP_PORT="):
        out.append("ARGUS_HTTP_PORT=8787")
        has_port = True
    else:
        out.append(ln)
if not has_port:
    out.append("ARGUS_HTTP_PORT=8787")
env_path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
print("ARGUS_HTTP_PORT=8787")
PY

python3 <<PY
from pathlib import Path

env_path = Path("$ENV_FILE")
lines = env_path.read_text(encoding="utf-8").splitlines()
out = []
has_mesh = False
for ln in lines:
    if ln.startswith("ARGUS_MESH_URL="):
        has_mesh = True
    out.append(ln)
if not has_mesh:
    out.append("ARGUS_MESH_URL=http://127.0.0.1:8090")
env_path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
if not has_mesh:
    print("ARGUS_MESH_URL=http://127.0.0.1:8090")
PY

# Wire Alien Monitor run feed (ARGUS → POST /api/argus/run). Token must match monitor ALIEN_API_TOKEN.
ROOT_ENV="$ROOT/.env"
MONITOR_TOKEN=""
MONITOR_URL="${ALIEN_MONITOR_URL:-https://magic-ai-factory.com/monitor}"
if [[ -f "$ROOT_ENV" ]]; then
  MONITOR_TOKEN="$(grep -E '^ALIEN_API_TOKEN=' "$ROOT_ENV" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' || true)"
fi
if [[ -z "$MONITOR_TOKEN" ]]; then
  MONITOR_TOKEN="$(grep -E '^ALIEN_API_TOKEN=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' || true)"
fi
if [[ -z "$MONITOR_TOKEN" ]] && command -v openssl >/dev/null 2>&1; then
  MONITOR_TOKEN="$(openssl rand -hex 24)"
  echo "Generated ALIEN_API_TOKEN for monitor ↔ argus run feed"
  if [[ -f "$ROOT_ENV" ]]; then
    echo "ALIEN_API_TOKEN=$MONITOR_TOKEN" >> "$ROOT_ENV"
  fi
fi

python3 <<PY
from pathlib import Path

env_path = Path("$ENV_FILE")
lines = env_path.read_text(encoding="utf-8").splitlines()
out = []
seen_url = seen_tok = False
token = "$MONITOR_TOKEN".strip()
url = "$MONITOR_URL".strip().rstrip("/")
for ln in lines:
    if ln.startswith("ALIEN_MONITOR_URL=") or ln.startswith("MONITOR_URL="):
        if not seen_url:
            out.append(f"ALIEN_MONITOR_URL={url}")
            seen_url = True
        continue
    if ln.startswith("ALIEN_API_TOKEN=") or ln.startswith("ALIEN_MONITOR_API_TOKEN="):
        if not seen_tok and token:
            out.append(f"ALIEN_API_TOKEN={token}")
            seen_tok = True
        continue
    out.append(ln)
if not seen_url:
    out.extend(["", f"ALIEN_MONITOR_URL={url}"])
if not seen_tok and token:
    out.append(f"ALIEN_API_TOKEN={token}")
env_path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
print(f"ALIEN_MONITOR_URL={url}")
if token:
    print("ALIEN_API_TOKEN=*** (synced from repo .env)")
else:
    print("WARN: ALIEN_API_TOKEN missing — set it in repo .env and re-run deploy_argus.sh")
PY

for port in 8787 8788; do
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" 2>/dev/null || true
  fi
done
sleep 1

cd "$ARGUS"
docker compose up -d --build --force-recreate argus argus-uni

echo "Waiting for ARGUS health..."
for _ in $(seq 1 40); do
  if curl -sf "http://127.0.0.1:8787/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
curl -sf "http://127.0.0.1:8787/health" | head -c 300 || {
  echo "ERROR: ARGUS live not healthy on :8787" >&2
  docker compose logs --tail=50 argus
  exit 1
}
echo ""
for _ in $(seq 1 20); do
  curl -sf "http://127.0.0.1:8788/health" >/dev/null 2>&1 && break
  sleep 2
done
curl -sf "http://127.0.0.1:8788/health" | head -c 300 || {
  echo "WARN: ARGUS uni not healthy on :8788 (Anvil on host :8545 required)" >&2
  docker compose logs --tail=30 argus-uni || true
}
echo ""
echo "ARGUS LIVE: http://127.0.0.1:8787/health"
echo "Arena LIVE: http://127.0.0.1:8787/arena"
echo "ARGUS UNI:  http://127.0.0.1:8788/health"
echo "Arena UNI:  http://127.0.0.1:8788/arena"

echo ""
echo "Verifying Alien Monitor run feed from ARGUS container..."
if [[ -n "$MONITOR_TOKEN" ]]; then
  FEED_OK=0
  for _ in $(seq 1 15); do
    if docker exec argus node -e "
const url='${MONITOR_URL%/}';
const token='${MONITOR_TOKEN}';
const payload={id:'deploy_probe_'+Date.now(),goal:'deploy_argus.sh feed probe',beats:[{kind:'receipt',title:'Feed probe',detail:'POST from ARGUS container',meta:'deploy ✓',status:'sealed'}],spendUsd:0,receiptHash:'probe',signer:'deploy'};
fetch(url+'/api/argus/run',{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify(payload)})
  .then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1));
" 2>/dev/null; then
      FEED_OK=1
      break
    fi
    sleep 2
  done
  if [[ "$FEED_OK" == "1" ]]; then
    echo "OK  ARGUS → Monitor feed (POST /api/argus/run via ${MONITOR_URL})"
  else
    echo "WARN: ARGUS container could not POST to ${MONITOR_URL} — check ALIEN_API_TOKEN and nginx /monitor/" >&2
    docker compose logs --tail=20 argus || true
  fi
else
  echo "WARN: skip feed probe — ALIEN_API_TOKEN not set"
fi

ensure_nginx_argus_routes() {
  if [[ ! -f "$NGINX_SITE" ]] || [[ ! -f "$SNIPPET_ARGUS" ]]; then
    return 1
  fi
  sudo cp "$SNIPPET_ARGUS" /etc/nginx/snippets/argus-arena.conf
  python3 - "$NGINX_SITE" <<'PY'
import re
import sys
from pathlib import Path

site = Path(sys.argv[1])
text = site.read_text(encoding="utf-8")
marker = "    location / {"
if marker not in text:
    raise SystemExit(f"Could not find insertion point in {site}")

includes = (
    "    include /etc/nginx/snippets/argus-landing.conf;\n"
    "    include /etc/nginx/snippets/argus-arena.conf;\n\n"
)

# Drop legacy inline arena/argus blocks when snippet includes are present (deploy re-run safe).
if "argus-arena.conf" in text:
    text = re.sub(
        r"\n# ARGUS Agent Arena.*?\n(?=    location / \{)",
        "\n",
        text,
        count=1,
        flags=re.DOTALL,
    )
    if "argus-landing.conf" not in text:
        text = text.replace(marker, includes + marker, 1)
    site.write_text(text, encoding="utf-8")
    print(f"nginx: {site} uses argus-arena.conf include (inline duplicate stripped if any)")
    raise SystemExit(0)

if "location = /arena" not in text and "argus-arena.conf" not in text:
    text = text.replace(marker, includes + marker, 1)
    site.write_text(text, encoding="utf-8")
    print(f"Patched {site} (argus landing + arena snippet includes)")
    raise SystemExit(0)

print(f"nginx: arena + argus routes already configured in {site}")
PY
}

ensure_nginx_argus_routes || true

if [[ -x "$ROOT/scripts/setup-argus-landing.sh" ]]; then
  sudo "$ROOT/scripts/setup-argus-landing.sh" || true
fi

if [[ -x "$ROOT/scripts/setup-argus-install.sh" ]]; then
  sudo "$ROOT/scripts/setup-argus-install.sh" || true
fi

if command -v nginx >/dev/null 2>&1 && [[ -f "$NGINX_SITE" ]]; then
  sudo nginx -t
  sudo systemctl reload nginx
fi

# Monitor card link (optional — merge into repo .env for next monitor deploy).
ROOT_ENV="$ROOT/.env"
if [[ -f "$ROOT_ENV" ]]; then
  python3 <<PY
from pathlib import Path
p = Path("$ROOT_ENV")
lines = p.read_text(encoding="utf-8").splitlines()
out, seen = [], False
for ln in lines:
    if ln.startswith("ALIEN_PUBLIC_ARGUS_URL=") or ln.startswith("ARGUS_PUBLIC_URL="):
        if not seen:
            out.append("ALIEN_PUBLIC_ARGUS_URL=$PUBLIC_ARGUS_ARENA")
            out.append("ARGUS_PUBLIC_URL=$PUBLIC_ARGUS_ARENA")
            seen = True
        continue
    out.append(ln)
if not seen:
    out.extend(["", "ALIEN_PUBLIC_ARGUS_URL=$PUBLIC_ARGUS_ARENA", "ARGUS_PUBLIC_URL=$PUBLIC_ARGUS_ARENA"])
p.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
print("Updated ALIEN_PUBLIC_ARGUS_URL in .env")
PY
fi

echo ""
echo "Public ARGUS landing: https://magic-ai-factory.com/argus/"
echo "Public Arena LIVE: $PUBLIC_ARGUS_ARENA"
echo "Public Arena UNI:  ${PUBLIC_ARGUS_ARENA%/arena}/arena-uni/"
echo "Arena stats LIVE:  ${PUBLIC_ARGUS_ARENA%/arena}/arena/stats"
echo "Arena stats UNI:   ${PUBLIC_ARGUS_ARENA%/arena}/arena-uni/stats"
