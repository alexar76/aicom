#!/usr/bin/env bash
# Emit a minimal .env.example for trimmed alexar76/aicom (VPS / factory-only checkout).
# Full template stays at repo root .env.example (790+ lines).
#
# Usage:
#   ./scripts/generate_trimmed_env_example.sh > .env.vps.example
#   ./scripts/generate_trimmed_env_example.sh --write   # writes .env.vps.example in repo root
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WRITE=0
[[ "${1:-}" == "--write" ]] && WRITE=1

emit() {
  cat <<'EOF'
# AI-Factory trimmed VPS — copy to .env and fill secrets (chmod 600)
# Full reference: .env.example in monorepo or docs/deploy-vps-trimmed.md

# ── Public URLs ───────────────────────────────────────────────────────────────
NEXT_PUBLIC_SITE_URL=https://magic-ai-factory.com
AIFACTORY_PUBLIC_URL=https://magic-ai-factory.com

# ── Factory admin (first boot) ────────────────────────────────────────────────
# JWT signing (>=32 chars). Docker entrypoint creates data/secrets/jwt_secret.key if unset.
# JWT_SECRET_KEY=
#
# First admin password: interactive TTY on `docker compose up` OR one-line file:
#   echo 'your-strong-password' > data/secrets/bootstrap_admin.txt && chmod 600 data/secrets/bootstrap_admin.txt
# See docs/security.md — no default password in repo.

# ── LLM (at least one) ───────────────────────────────────────────────────────
DEEPSEEK_API_KEY=
# ANTHROPIC_API_KEY=

# ── Ecosystem co-located on same host ─────────────────────────────────────────
ALIEN_MODE=universe
# Monitor binds 127.0.0.1 by default — nginx proxies /monitor/. For direct :9100 without nginx:
# ALIEN_HOST=0.0.0.0
ALIEN_PORT=9100
ALIEN_API_TOKEN=
ALIEN_PUBLIC_READ=1

HUB_URL=http://127.0.0.1:9083
AIMARKET_ADMIN_TOKEN=
AIMARKET_ALLOW_LOCAL_PUBLISH=0

MESH_HUB_URL=http://127.0.0.1:9083
MESH_API_TOKEN=
MESH_ADMIN_TOKEN=
MESH_PUBLIC_READ=0

AICOM_API_URL=http://127.0.0.1:9081
PROMETHEUS_URL=http://127.0.0.1:9090

# Hub in Docker → host-side hello-capability on 127.0.0.1 (dev / UNI demos)
AIMARKET_INVOKE_HOST_GATEWAY=host.docker.internal

# UNI grants (Monitor hub liquidity) — same value on Factory + Monitor
# AIFACTORY_UNI_GRANT_SECRET=

# Crypto (optional — paid invoke + on-chain LIVE nodes)
# AIFACTORY_CRYPTO_ENABLED=0

# ── Docker image tags (CI / rebuild) ──────────────────────────────────────────
# AICOM_IMAGE_TAG=prod-YYYYMMDD-gitsha   # scripts/docker_image_tag.sh

# ── Deploy helpers ────────────────────────────────────────────────────────────
# ./scripts/ci_fetch_factory_test_deps.sh     # clone acex, aimarket-hub, plugins for CI
# ./scripts/ensure_deploy_satellites.sh       # same for VPS full ecosystem deploy
# ./scripts/deploy_ecosystem.sh
# ./scripts/verify_ecosystem_full.sh
EOF
}

if [[ "$WRITE" -eq 1 ]]; then
  emit > "$ROOT/.env.vps.example"
  echo "Wrote $ROOT/.env.vps.example"
else
  emit
fi
