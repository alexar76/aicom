#!/bin/bash
# Production stack: PostgreSQL + split services + prod guards (docker-compose.prod.yml).
#
# Usage:
#   cp .env.example .env   # if needed
#   python3 scripts/fill_production_env.py --env-file .env --public-url https://your-host
#   ./scripts/run_prod_compose.sh up -d --build
#   ./scripts/run_prod_compose.sh --logs
#   ./scripts/run_prod_compose.sh --down
#
# After healthy:
#   ./scripts/load_test_factory.sh --base-url http://127.0.0.1:9081 --duration 600

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

compose_cmd() {
  if docker compose version &>/dev/null; then
    echo "docker compose"
    return
  fi
  echo -e "${RED}Docker Compose V2 required (docker compose).${NC}" >&2
  exit 1
}

COMPOSE=$(compose_cmd)
COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.prod.yml)

ensure_env() {
  if [[ ! -f .env ]]; then
    echo -e "${YELLOW}No .env — creating from .env.example${NC}"
    cp .env.example .env
  fi
  python3 ./scripts/fill_production_env.py --env-file .env "${@}" 2>/dev/null || true
  # shellcheck disable=SC1091
  set -a && source .env && set +a
  if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
    echo -e "${RED}POSTGRES_PASSWORD is required. Run: python3 scripts/fill_production_env.py --env-file .env${NC}" >&2
    exit 2
  fi
  if [[ -z "${GRAFANA_ADMIN_PASSWORD:-}" ]]; then
    echo -e "${RED}GRAFANA_ADMIN_PASSWORD is required. Run: python3 scripts/fill_production_env.py --env-file .env${NC}" >&2
    exit 2
  fi
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  echo "Usage: ./scripts/run_prod_compose.sh [up|down|logs|ps] [compose args...]"
  echo "       ./scripts/run_prod_compose.sh --down"
  echo "       ./scripts/run_prod_compose.sh --logs"
  echo ""
  echo "Production overlay: Postgres + split API/frontend/workers + AIFACTORY_PROD=1"
  exit 0
fi

if [[ "${1:-}" == "--down" ]]; then
  echo -e "${YELLOW}Stopping production stack...${NC}"
  $COMPOSE "${COMPOSE_FILES[@]}" down
  echo -e "${GREEN}✓ Stopped${NC}"
  exit 0
fi

if [[ "${1:-}" == "--logs" ]]; then
  $COMPOSE "${COMPOSE_FILES[@]}" logs -f
  exit 0
fi

./scripts/init-compose-volumes.sh || true
ensure_env

echo -e "${CYAN}══════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  AI-Factory — production stack (Postgres + split)${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════════${NC}"

$COMPOSE "${COMPOSE_FILES[@]}" up -d "${@}"

FRONT="${AICOM_PORT_FRONTEND:-9080}"
APIP="${AICOM_PORT_API:-9081}"

echo ""
echo -e "${GREEN}✓ Production stack is up.${NC}"
echo ""
echo -e "  ${CYAN}App:${NC}  http://localhost:${FRONT}"
echo -e "  ${CYAN}API:${NC}  http://localhost:${APIP}/api/health"
echo ""
echo -e "  ${YELLOW}Load test:${NC} ./scripts/load_test_factory.sh --base-url http://127.0.0.1:${APIP}"
echo -e "  ${YELLOW}Logs:${NC}      ./scripts/run_prod_compose.sh --logs"
echo ""
