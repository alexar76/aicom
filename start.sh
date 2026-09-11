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
#   ./start.sh --everything    # ALL ~40 containers of all three prod hosts, one box
#   ./start.sh --help
#
# Tiers, because 40 containers on a laptop is a choice and not a default:
#   core        (no flag)      7 containers · ~15 GB disk · ~6 GB RAM · 2 cores
#   --full                     the deploy-engine path (Factory, Hub, Mesh, ARGUS,
#                              Monitor, Pulse) — unchanged, still the deploy route
#   --everything               all three prod hosts collapsed onto one machine:
#                              ~40 containers · >=60 GB disk · >=16 GB RAM · 4 cores
#                              → scripts/everything.sh (+ docker-compose.everything.yml)
#                              Extra flags there: --bind <addr>, --host-ip <addr>,
#                              --reset-chain, --yes, --skip-resource-check
# ============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# ── pretty + shared helpers ─────────────────────────────────────────────────
# Colours, say/step/ok/warn/die, gen_hex, ensure_secret, wait_http and open_url
# live in scripts/lib/common.sh so the core tier and the everything tier cannot
# drift apart on how a secret is minted or read back — a divergence there shows
# up as "the core tier generated a token the full tier cannot find".
if [[ ! -f "$ROOT/scripts/lib/common.sh" ]]; then
  echo "scripts/lib/common.sh is missing — this checkout is incomplete." >&2
  exit 1
fi
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.core.yml)

# ── args ──────────────────────────────────────────────────────────────────
BUILD=1; OPEN=1; ACTION="up"
FULL_ARGS=()
# --everything is order-independent on purpose: `--everything --down` and
# `--down --everything` must both work, so it sets a flag and dispatches after
# the loop instead of exec-ing on sight the way --full does.
TIER="core"; EVERYTHING_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --full)       shift; exec "$ROOT/scripts/quickstart_ecosystem.sh" "$@" ;;
    --everything) TIER="everything"; shift ;;
    --no-build)   BUILD=0; EVERYTHING_ARGS+=(--no-build); shift ;;
    --no-open)    OPEN=0;  EVERYTHING_ARGS+=(--no-open);  shift ;;
    --logs)       ACTION="logs"; EVERYTHING_ARGS+=(--logs); shift ;;
    --down)       ACTION="down"; EVERYTHING_ARGS+=(--down); shift ;;
    # everything-tier only — see the guard below for why they are not accepted
    # for core (core's compose pins the Factory to 127.0.0.1 by design).
    # The explicit arity check matters: `shift 2` with one argument left returns
    # non-zero, and under `set -e` that exits 0-ish and SILENTLY — the user is
    # told nothing and assumes the stack came up.
    --bind)       [[ $# -ge 2 ]] || die "--bind needs an address, e.g. --bind 0.0.0.0"
                  EVERYTHING_ARGS+=(--bind "$2"); TIER_ONLY=1; shift 2 ;;
    --host-ip)    [[ $# -ge 2 ]] || die "--host-ip needs an address, e.g. --host-ip 203.0.113.7"
                  EVERYTHING_ARGS+=(--host-ip "$2"); TIER_ONLY=1; shift 2 ;;
    --reset-chain|--yes|-y|--skip-resource-check)
                  EVERYTHING_ARGS+=("$1"); TIER_ONLY=1; shift ;;
    # `--everything --help` should describe the everything tier, not this one.
    # 2,29 = the header block, minus its top and bottom rule lines. Keep this in
    # step with the header when editing it (`set -euo pipefail` is line 31).
    -h|--help)    if [[ "$TIER" == "everything" ]]; then exec "$ROOT/scripts/everything.sh" --help; fi
                  sed -n '2,29p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "Unknown option: $1  (see ./start.sh --help)" ;;
  esac
done

if [[ "$TIER" == "everything" ]]; then
  [[ -x "$ROOT/scripts/everything.sh" ]] || die "scripts/everything.sh missing or not executable."
  exec "$ROOT/scripts/everything.sh" "${EVERYTHING_ARGS[@]}"
fi
if [[ "${TIER_ONLY:-0}" -eq 1 ]]; then
  die "--bind / --host-ip / --reset-chain / --yes / --skip-resource-check apply to --everything only.
   Core publishes the Factory on 127.0.0.1 by design and has no ~40-container preflight to skip."
fi

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

# The public mirror (github.com/alexar76/aicom) ships this script and
# docker-compose.core.yml but strips the three satellite build contexts, because each
# satellite is published as its own repository. Cloning the mirror and running the
# headline command therefore used to die on "Dockerfile not found" — a first impression
# that reads as "this project does not work". Degrade to the tier that IS present and
# say exactly what is missing and where to get it.
missing_ctx=()
[[ -f "$ROOT/aimarket-hub/Dockerfile" ]]            || missing_ctx+=("aimarket-hub")
[[ -f "$ROOT/ai-service-mesh/backend/Dockerfile" ]] || missing_ctx+=("ai-service-mesh")
[[ -f "$ROOT/alien-monitor/Dockerfile" ]]           || missing_ctx+=("alien-monitor")
if (( ${#missing_ctx[@]} )); then
  COMPOSE=(docker compose -f docker-compose.yml)
  warn "Not in this checkout: ${missing_ctx[*]} — starting the Factory alone."
  say "${DIM}  Each is published separately; clone them beside this repo to get the full core tier:${N}"
  for s in "${missing_ctx[@]}"; do
    say "${DIM}    git clone https://github.com/alexar76/${s}.git${N}"
  done
  say "${DIM}  Or skip installing anything: paste https://modelmarket.dev/mcp into an MCP${N}"
  say "${DIM}  client and call the live hub directly — docs/hosted-mcp-endpoint.md${N}"
  say ""
fi

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

# gen_hex / ensure_secret come from scripts/lib/common.sh — same minting the
# everything tier uses, so a .env written by either tier is readable by both.
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

# ── 4a. model-id gate ────────────────────────────────────────────────────────
# Placed AFTER the config is seeded and BEFORE anything is built, because the
# failure it catches is silent: the stack comes up, health checks pass, and every
# generation fails at the first call. It asks the provider with a one-token call
# rather than reading a listing — the two disagree (DeepSeek answers a retired
# `deepseek-chat` with `deepseek-v4-flash`; OpenRouter refuses a retired id outright).
# An unreachable provider never blocks: see model_id_gate in scripts/lib/common.sh.
step "Model ids"
model_id_gate "$ROOT"

# ── 4b. remote satellites: say it out loud ──────────────────────────────────
# The core tier starts four services; the other satellites on the ecosystem map
# are read from our PUBLIC read-only endpoints so the map is not two-thirds dead
# (docker-compose.core.yml's "Remote satellites" block — a deliberate choice, not
# a leak). But a stack that quietly calls someone else's servers is a thing the
# operator has a right to know about before it happens, not after, so it is
# printed rather than left in a compose comment nobody opens.
#
# The full local alternative is the everything tier, which BUILDS those satellites
# and calls nothing of ours — `./start.sh --everything`.
step "Remote satellites"
REMOTE_VARS=(ALIEN_ORACLE_PORTAL ALIEN_ORACLE_PLATON_URL ALIEN_ORACLE_FAMILY_URL
             ALIEN_METIS_URL ALIEN_SKOPOS_URL ALIEN_HELIOS_URL ALIEN_DIOSCURI_URL)
if [[ "${ECO_NO_REMOTE:-0}" == "1" ]]; then
  # `${VAR:-default}` falls back on empty as well as unset, so blanking these
  # would silently restore the defaults. Point them at the discard port instead:
  # refused immediately, no hang, and the panels take the documented idle path.
  for v in "${REMOTE_VARS[@]}"; do export "$v=http://127.0.0.1:9"; done
  ok "ECO_NO_REMOTE=1 — fully local; the satellite panels will sit idle"
else
  say "  ${DIM}The map reads six satellites from our public read-only endpoints${N}"
  say "  ${DIM}(oracles/metis/skopos/helios/dioscuri.modelmarket.dev, magic-ai-factory.com).${N}"
  say "  ${DIM}Nothing is sent to them beyond the requests themselves, and the stack${N}"
  say "  ${DIM}works offline — those panels just idle.${N}"
  say "  ${DIM}Fully local instead:  ECO_NO_REMOTE=1 ./start.sh   (panels idle)${N}"
  say "  ${DIM}Or run them for real: ./start.sh --everything      (builds all of them)${N}"
fi

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
# wait_http comes from scripts/lib/common.sh.
say ""
step "Health"
wait_http "Factory API" "http://localhost:9081/api/health"                90 || warn "Factory slow to start — check: ./start.sh --logs"
# Only for the tiers that were actually started. Waiting three minutes on a hub and a
# monitor this run deliberately skipped reads as a hang, and it lands on exactly the
# person the degraded tier exists for.
if (( ${#missing_ctx[@]} == 0 )); then
  wait_http "Hub"       "http://localhost:9083/.well-known/ai-market.json" 60 || warn "Hub slow to start"
  # Monitor in universe mode deploys a local Anvil chain — give it longer, best-effort.
  wait_http "Monitor"   "http://localhost:9100/api/health"                120 || warn "Monitor still deploying its universe — it will be live at :9100/monitor/ shortly"
fi

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
# Printing a URL for a service this run skipped is worse than printing nothing: the reader
# clicks it, gets connection refused, and concludes the whole stack is broken.
if (( ${#missing_ctx[@]} == 0 )); then
  say "  ${B}Monitor${N}    ${C}http://localhost:9100/monitor/${N}      live universe · reputation graph · contours"
  say "  ${B}Hub${N}        ${C}http://localhost:9083${N}          federation / marketplace"
  say "  ${B}Mesh API${N}   ${C}http://localhost:8090${N}"
else
  say "  ${DIM}Not started (not in this checkout): ${missing_ctx[*]}${N}"
  say "  ${B}Live hub${N}   ${C}https://modelmarket.dev/mcp${N}     the marketplace, hosted — paste into an MCP client"
fi
say "  ${B}Metrics${N}    ${C}http://localhost:9090/prometheus/${N}"
say ""
say "  ${DIM}stop: ./start.sh --down · logs: ./start.sh --logs · whole fleet: ./start.sh --full${N}"
say "  ${DIM}every satellite too (~40 containers): ./start.sh --everything${N}"
say ""

# ── 8. open browser ───────────────────────────────────────────────────────
if [[ "$OPEN" -eq 1 ]]; then
  open_url "http://localhost:9080/admin/login"
fi
