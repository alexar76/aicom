#!/bin/bash
# ============================================================================
# AI-Factory v2.1 — Docker Compose Launcher
# ============================================================================
# Requires Docker Compose V2 (`docker compose`). Ubuntu:
#   sudo apt-get install -y docker-compose-plugin
# Old `docker-compose` (Python v1) breaks with modern Docker (ContainerConfig).
#
# Usage:
#   ./scripts/init-compose-volumes.sh   # once on host (sudo if needed)
#   ./run-compose.sh                  — Start stack
#   ./run-compose.sh --build          — Rebuild images
#   ./run-compose.sh --down           — Stop services (keeps ./data)
#   ./run-compose.sh --down-volumes   — Stop and remove named volumes (destructive)
#   ./run-compose.sh --logs           — Tail logs
# ============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

compose_cmd() {
  if docker compose version &>/dev/null; then
    echo "docker compose"
    return
  fi
  if command -v docker-compose &>/dev/null; then
    echo -e "${RED}Warning:${NC} using legacy docker-compose. Install V2: sudo apt-get install -y docker-compose-plugin" >&2
    echo "docker-compose"
    return
  fi
  echo -e "${RED}Neither 'docker compose' nor docker-compose' found.${NC}" >&2
  exit 1
}

COMPOSE=$(compose_cmd)

resolve_compose_files() {
  COMPOSE_FILES=(-f docker-compose.yml)
  if [[ -d data/secrets/llm ]] && compgen -G "data/secrets/llm/*_api_key" >/dev/null 2>&1; then
    COMPOSE_FILES+=(-f docker-compose.secrets.yml)
  fi
}

ensure_env_for_stack() {
  if [[ ! -f .env ]]; then
    echo -e "${YELLOW}No .env — creating from .env.example (add LLM keys before pipeline work).${NC}"
    cp .env.example .env
  fi
  if [[ -f .env ]]; then
    python3 ./scripts/fill_production_env.py --env-file .env 2>/dev/null || true
    # shellcheck disable=SC1091
    set -a && source .env && set +a
  fi
  if [[ -z "${GRAFANA_ADMIN_PASSWORD:-}" ]]; then
    echo -e "${RED}GRAFANA_ADMIN_PASSWORD is required. Run: python3 scripts/fill_production_env.py --env-file .env${NC}" >&2
    exit 2
  fi
}

# ── Help ────────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--help" ]]; then
    echo "Usage: ./run-compose.sh [--build] [--down] [--down-volumes] [--logs]"
    echo ""
    echo "First-time host prep (fixes Prometheus/Grafana bind-mount permissions):"
    echo "  ./scripts/init-compose-volumes.sh"
    echo "  sudo ./scripts/init-compose-volumes.sh   # if not root"
    echo ""
    echo "Copy env: cp .env.example .env  (optional: ports, Grafana password)"
    echo ""
    echo "URLs (defaults):"
    echo "  App:        http://localhost:\${AICOM_PORT_FRONTEND:-9080}"
    echo "  API:        http://localhost:\${AICOM_PORT_API:-9081}/api/health"
    echo "  Prometheus: http://localhost:\${AICOM_PORT_PROMETHEUS:-9090}"
    echo "  Grafana:    http://localhost:\${AICOM_PORT_GRAFANA:-9082}"
    exit 0
fi

# ── Down ────────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--down" ]]; then
    resolve_compose_files
    echo -e "${YELLOW}Stopping services...${NC}"
    $COMPOSE "${COMPOSE_FILES[@]}" down
    echo -e "${GREEN}✓ Stopped${NC}"
    exit 0
fi

if [[ "${1:-}" == "--down-volumes" ]]; then
    echo -e "${RED}Removing containers and Docker-named volumes (bind-mount ./data kept)...${NC}"
    resolve_compose_files
    $COMPOSE "${COMPOSE_FILES[@]}" down -v
    echo -e "${GREEN}✓ Down${NC}"
    exit 0
fi

# ── Logs ────────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--logs" ]]; then
    echo -e "${CYAN}Tailing logs...${NC}"
    resolve_compose_files
    $COMPOSE "${COMPOSE_FILES[@]}" logs -f
    exit 0
fi

# ── Start ───────────────────────────────────────────────────────────────────
echo -e "${CYAN}══════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  AI-Factory v2.1 — Docker Compose${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════════${NC}"

./scripts/init-compose-volumes.sh || true

ensure_env_for_stack
resolve_compose_files

BUILD_FLAG=()
if [[ "${1:-}" == "--build" ]]; then
    BUILD_FLAG=(--build)
    echo -e "${YELLOW}Build requested${NC}"
fi

echo -e "${YELLOW}Starting...${NC}"
$COMPOSE "${COMPOSE_FILES[@]}" up -d "${BUILD_FLAG[@]}"

FRONT="${AICOM_PORT_FRONTEND:-9080}"
APIP="${AICOM_PORT_API:-9081}"
PROM="${AICOM_PORT_PROMETHEUS:-9090}"
GRAF="${AICOM_PORT_GRAFANA:-9082}"

echo ""
echo -e "${GREEN}✓ Stack is up.${NC}"
echo ""
echo -e "  ${CYAN}App:${NC}        http://localhost:${FRONT}"
echo -e "  ${CYAN}API:${NC}        http://localhost:${APIP}/api/health"
echo -e "  ${CYAN}Metrics:${NC}    http://localhost:${APIP}/metrics"
echo -e "  ${CYAN}Prometheus:${NC} http://localhost:${PROM}"
echo -e "  ${CYAN}Grafana:${NC}    http://localhost:${GRAF}"
echo ""
echo -e "  ${YELLOW}Admin:${NC}   user admin — password: data/secrets/bootstrap_admin.txt (first headless start) or your TTY bootstrap"
echo -e "  ${YELLOW}Grafana:${NC} \${GRAFANA_ADMIN_USER:-admin} / (see GRAFANA_ADMIN_PASSWORD in .env)"
echo ""
echo -e "  ${YELLOW}Logs:${NC}    ./run-compose.sh --logs"
echo -e "  ${YELLOW}Stop:${NC}    ./run-compose.sh --down"
echo ""
