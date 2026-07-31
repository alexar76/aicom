#!/usr/bin/env bash
# ============================================================================
# AI-Factory — one door.  ./start.sh
# ============================================================================
# The "make it rain, safely" button. One command brings up the CORE stack:
#
#     Factory (real AI pipeline)  +  Hub  +  Service Mesh  +  Alien Monitor
#
# You supply ONE LLM key. Everything else is generated for you. Crypto/mainnet
# stays OFF (no real funds). The full 15-satellite fleet is one flag away.
#
#   ./start.sh                 # bring up core (build if needed), open browser
#   ./start.sh --no-build      # reuse existing images (faster)
#   ./start.sh --no-open       # don't open a browser
#   ./start.sh --logs          # tail core logs
#   ./start.sh --down          # stop core (keeps ./data + volumes)
#   ./start.sh --full [...]    # the whole ecosystem → scripts/quickstart_ecosystem.sh
#   ./start.sh --help
# ============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# ── pretty ──────────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  B=$'\033[1m'; DIM=$'\033[2m'; R=$'\033[0;31m'; G=$'\033[0;32m'; Y=$'\033[1;33m'; C=$'\033[0;36m'; N=$'\033[0m'
else
  B=""; DIM=""; R=""; G=""; Y=""; C=""; N=""
fi
say()  { printf '%s\n' "$*"; }
step() { printf '%s▶%s %s\n' "$C" "$N" "$*"; }
ok()   { printf '%s✓%s %s\n' "$G" "$N" "$*"; }
warn() { printf '%s!%s %s\n' "$Y" "$N" "$*" >&2; }
die()  { printf '%s✗ %s%s\n' "$R" "$*" "$N" >&2; exit 1; }

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.core.yml)

# ── args ──────────────────────────────────────────────────────────────────
BUILD=1; OPEN=1; ACTION="up"
FULL_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --full)      shift; exec "$ROOT/scripts/quickstart_ecosystem.sh" "$@" ;;
    --no-build)  BUILD=0; shift ;;
    --no-open)   OPEN=0; shift ;;
    --logs)      ACTION="logs"; shift ;;
    --down)      ACTION="down"; shift ;;
    -h|--help)   sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "Unknown option: $1  (see ./start.sh --help)" ;;
  esac
done

# ── simple actions ──────────────────────────────────────────────────────────
if [[ "$ACTION" == "logs" ]]; then exec "${COMPOSE[@]}" logs -f --tail=120; fi
if [[ "$ACTION" == "down" ]]; then
  step "Stopping core stack (data + volumes kept)…"
  "${COMPOSE[@]}" down
  ok "Core stopped. Data preserved in ./data. Restart with ./start.sh"
  exit 0
fi

say ""
say "${B}=== AI-Factory · core stack ===${N}"
say "${DIM}Factory + Hub + Mesh + Alien Monitor · crypto OFF · one LLM key${N}"
say ""

# ── 1. preflight ──────────────────────────────────────────────────────────
step "Preflight"
command -v docker >/dev/null 2>&1 || die "Docker not found. Install Docker Engine / Desktop first."
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 required ('docker compose', not 'docker-compose')."
docker info >/dev/null 2>&1 || die "Docker daemon not reachable — is Docker running?"
ok "docker + compose v2"

# ── 2. .env ─────────────────────────────────────────────────────────────────
if [[ ! -f .env ]]; then
  if [[ -f .env.demo ]]; then
    cp .env.demo .env
    ok "Created .env from .env.demo"
  else
    warn "No .env and no .env.demo — creating an empty .env"
    : > .env
  fi
fi

# append KEY=<generated> to .env only if KEY is not already set (non-empty)
gen_hex() { python3 -c "import secrets;print(secrets.token_hex(${1:-24}))" 2>/dev/null || openssl rand -hex "${1:-24}"; }
ensure_secret() {
  local key="$1" val="$2"
  if grep -qE "^${key}=.+" .env 2>/dev/null; then return 0; fi
  # remove any empty definition, then append
  if grep -qE "^${key}=" .env 2>/dev/null; then
    grep -vE "^${key}=" .env > .env.tmp && mv .env.tmp .env
  fi
  printf '%s=%s\n' "$key" "$val" >> .env
  say "  ${DIM}generated ${key}${N}"
}

step "Secrets (auto-generated, stored in .env — never committed)"
ensure_secret GRAFANA_ADMIN_PASSWORD "$(gen_hex 18)"
ensure_secret MESH_API_TOKEN         "$(gen_hex 24)"
ensure_secret MESH_ADMIN_TOKEN       "$(gen_hex 24)"
ensure_secret ALIEN_API_TOKEN        "$(gen_hex 24)"
ensure_secret AIFACTORY_DEV_BOOTSTRAP_PASSWORD "$(gen_hex 12)"
chmod 600 .env 2>/dev/null || true
ok "Secrets ready"

# ── 3. LLM key check (the ONE thing you provide) ──────────────────────────────
has_llm_key=0
for k in DEEPSEEK_API_KEY ANTHROPIC_API_KEY OPENAI_API_KEY TOGETHER_API_KEY GROQ_API_KEY; do
  if grep -qE "^${k}=.+" .env 2>/dev/null; then has_llm_key=1; break; fi
done
if ls data/secrets/llm/*_api_key >/dev/null 2>&1; then has_llm_key=1; fi
if [[ "$has_llm_key" -eq 0 ]]; then
  say ""
  warn "No LLM key found in .env."
  warn "The stack will boot and the Monitor works, but the AI pipeline will use the"
  warn "synthetic fallback (templated output) instead of real agents. For the real"
  warn "'wow', add ONE key to .env and re-run, e.g.:"
  warn "    ${B}DEEPSEEK_API_KEY=sk-...${N}   (or ANTHROPIC_API_KEY / OPENAI_API_KEY)"
  say ""
else
  ok "LLM key detected — real AI agents enabled"
fi

# ── 4. files the Monitor mounts ───────────────────────────────────────────────
step "Data dirs"
mkdir -p data/config data/alien-monitor/universe data/secrets
if [[ ! -f data/config/model_providers.yaml ]]; then
  if [[ -f data/config/model_providers.example.yaml ]]; then
    cp data/config/model_providers.example.yaml data/config/model_providers.yaml
    ok "Seeded data/config/model_providers.yaml from example"
  else
    warn "data/config/model_providers.example.yaml missing — Monitor LLM config mount may be empty"
    : > data/config/model_providers.yaml
  fi
fi
ok "Data dirs ready"

# ── 5. up ─────────────────────────────────────────────────────────────────
UP=(up -d)
if [[ "$BUILD" -eq 1 ]]; then
  step "Starting core stack (building images — first run takes a few minutes)"
  UP+=(--build)
else
  step "Starting core stack (reusing existing images)"
fi
"${COMPOSE[@]}" "${UP[@]}"

# ── 6. wait for health ────────────────────────────────────────────────────────
wait_http() { # name url timeout_s
  local name="$1" url="$2" timeout="${3:-90}" start elapsed
  start=$(date +%s)
  printf '  waiting for %s' "$name"
  while true; do
    if curl -fsS -m 3 "$url" >/dev/null 2>&1; then printf ' %s✓%s\n' "$G" "$N"; return 0; fi
    elapsed=$(( $(date +%s) - start ))
    if [[ "$elapsed" -ge "$timeout" ]]; then printf ' %s(still warming after %ss)%s\n' "$Y" "$timeout" "$N"; return 1; fi
    printf '.'; sleep 3
  done
}

say ""
step "Health"
wait_http "Factory API" "http://localhost:9081/api/health"                90 || warn "Factory slow to start — check: ./start.sh --logs"
wait_http "Hub"         "http://localhost:9083/.well-known/ai-market.json" 60 || warn "Hub slow to start"
# Monitor in universe mode deploys a local Anvil chain — give it longer, best-effort.
wait_http "Monitor"     "http://localhost:9100/api/health"                120 || warn "Monitor still deploying its universe — it will be live at :9100/monitor/ shortly"

# ── 7. report ─────────────────────────────────────────────────────────────
ADMIN_PW="$(grep -E '^AIFACTORY_DEV_BOOTSTRAP_PASSWORD=' .env | head -1 | cut -d= -f2-)"
# If a generated bootstrap file exists, prefer its password= line. The file is
# two lines (username=…\npassword=…), so parse the field — never read it whole.
if [[ -f data/secrets/bootstrap_admin.txt ]]; then
  _bp="$(grep -E '^password=' data/secrets/bootstrap_admin.txt | head -1 | cut -d= -f2- | tr -d '[:space:]')"
  [[ -n "$_bp" ]] && ADMIN_PW="$_bp"
fi

say ""
say "${G}${B}Core is up.${N}"
say ""
say "  ${B}Factory${N}    ${C}http://localhost:9080${N}          idea → real AI build"
say "  ${B}Admin${N}      ${C}http://localhost:9080/admin/login${N}   user ${B}admin${N} · pass ${B}${ADMIN_PW:-see docs/security.md}${N}"
say "  ${B}Monitor${N}    ${C}http://localhost:9100/monitor/${N}      live universe · reputation graph · contours"
say "  ${B}Hub${N}        ${C}http://localhost:9083${N}          federation / marketplace"
say "  ${B}Mesh API${N}   ${C}http://localhost:8090${N}"
say "  ${B}Metrics${N}    ${C}http://localhost:9090/prometheus/${N}"
say ""
say "  ${DIM}stop: ./start.sh --down · logs: ./start.sh --logs · whole fleet: ./start.sh --full${N}"
say ""

# ── 8. open browser ───────────────────────────────────────────────────────
if [[ "$OPEN" -eq 1 ]]; then
  URL="http://localhost:9080/admin/login"
  if command -v open >/dev/null 2>&1; then open "$URL" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1 || true
  fi
fi
