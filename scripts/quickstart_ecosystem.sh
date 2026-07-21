#!/usr/bin/env bash
# Greenfield onboarding wrapper for the full ecosystem.
#
# This is a thin convenience layer around scripts/deploy_ecosystem.sh — it does the
# boring preflight (Docker / Compose / .env), hands off to the real deploy engine,
# then prints the next steps (TLS, verify, oracle host, on-chain). It is NOT a new
# deploy engine; deploy_ecosystem.sh remains the source of truth.
#
# Usage:
#   ./scripts/quickstart_ecosystem.sh                                  # local fleet
#   ./scripts/quickstart_ecosystem.sh --public-url https://your-domain # production public
#   ./scripts/quickstart_ecosystem.sh --skip-verify                    # pass-through flags
#
# See docs/quickstart-ecosystem-deploy.md for the full tiered runbook.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*" >&2; }
die()  { printf '\033[31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

bold "=== Ecosystem quick-start (preflight) ==="

# 1) Docker + Compose v2
command -v docker >/dev/null 2>&1 || die "Docker not found. Install Docker Engine + Compose v2 first."
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 not found (need 'docker compose', not 'docker-compose')."
docker info >/dev/null 2>&1 || die "Docker daemon not reachable. Is it running / do you have permission?"
echo "  docker + compose v2: OK"

# 2) .env (LLM keys etc.)
if [[ ! -f "$ROOT/.env" ]]; then
  if [[ -f "$ROOT/.env.example" ]]; then
    warn "  No .env found. Copy and fill it before deploying:"
    warn "      cp .env.example .env   # then add your LLM API keys"
    die ".env is required (see .env.example)."
  fi
  die ".env not found and no .env.example to copy from."
fi
echo "  .env present: OK"

# 3) nginx — only needed for the public/TLS tier; just a heads-up.
PUBLIC_URL=""
args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
  if [[ "${args[i]}" == "--public-url" ]]; then PUBLIC_URL="${args[i+1]:-}"; fi
done
if [[ -n "$PUBLIC_URL" ]]; then
  command -v nginx >/dev/null 2>&1 || warn "  nginx not found — required for the public/TLS tier (Level 3). Install it before running the TLS one-shots."
  echo "  public URL: $PUBLIC_URL"
fi

# 4) Hand off to the real deploy engine (Factory -> Hub -> Mesh -> Monitor -> verify).
bold ""
bold "=== Deploying the fleet (scripts/deploy_ecosystem.sh) ==="
"$ROOT/scripts/deploy_ecosystem.sh" "$@"

# 5) Next steps.
bold ""
bold "=== Fleet up. Next steps ==="
cat <<EOF
  Local URLs:
    Factory   http://127.0.0.1:9080   (API :9081)
    Hub       http://127.0.0.1:9083
    Mesh      http://127.0.0.1:8090
    ARGUS     http://127.0.0.1:8787/health
    Monitor   http://127.0.0.1:9100      Pulse  http://127.0.0.1:5199
    Lottery   http://127.0.0.1:9195/healthz
    Landing   https://modeldev.modelmarket.dev/  (after deploy_ecosystem_landing + TLS)

  Re-verify any time:
    ./scripts/verify_ecosystem_full.sh        # 17+ smoke checks

  Full runbook: docs/quickstart-ecosystem-deploy.md
EOF
if [[ -n "$PUBLIC_URL" ]]; then
  cat <<EOF

  Public TLS (run on the factory host, as root):
    sudo CERTBOT_EMAIL=you@example.com ./scripts/setup-modelmarket-ssl.sh
    # + certbot for the factory domain — see docs/production-domain.md
EOF
fi
cat <<EOF

  Oracle host (Level 4 — separate machine by default):
    sudo CERTBOT_EMAIL=you@example.com ./scripts/setup-oracles-platon-on-host.sh
    ./scripts/announce-platon-oracles.sh      # federate from the factory host

  On-chain (optional, Base mainnet 8453):
    ./scripts/deploy_ecosystem_base.sh broadcast
    ./scripts/deploy_lottery_base.sh broadcast

  Not in fleet script: Metis, DIOSCURI, HELIOS — see quickstart-ecosystem-deploy.md §9
EOF
