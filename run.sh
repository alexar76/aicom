#!/bin/bash
# ============================================================================
# AUTONOMOUS AI-FACTORY v2.1 — Docker Run Script
# ============================================================================
# Builds (if needed) and runs the AI-Factory container with persistent data.
# All configs, pipeline state, logs, and secrets are stored in ~/aicom-data
# and survive container rebuilds.
#
# Usage:
#   ./run.sh            — Build & run (first time or after code changes)
#   ./run.sh --no-build — Run without rebuilding (use existing image)
#   ./run.sh --help     — Show this help
# ============================================================================

set -euo pipefail

IMAGE_NAME="ai-factory:latest"
CONTAINER_NAME="ai-factory"
DATA_DIR="${HOME}/aicom-data"
FRONTEND_PORT="${FRONTEND_PORT:-8080}"
BACKEND_PORT="${BACKEND_PORT:-8081}"

# ── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ── Help ────────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--help" ]]; then
    echo "Usage:"
    echo "  ./run.sh            — Build Docker image & run container"
    echo "  ./run.sh --no-build — Run without rebuilding"
    echo "  ./run.sh --help     — Show this help"
    echo ""
    echo "Environment variables:"
    echo "  FRONTEND_PORT  — Host port for frontend (default: 8080)"
    echo "  BACKEND_PORT   — Host port for backend  (default: 8081)"
    echo "  AIFACTORY_AUTONOMOUS_PIPELINE  — First run with this data dir: 1 = autonomous, 0 = ideas only (default, skips prompt)"
    exit 0
fi

# ── Step 1: Build (unless --no-build) ──────────────────────────────────────
if [[ "${1:-}" != "--no-build" ]]; then
    echo -e "${CYAN}══════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  Building Docker image: ${IMAGE_NAME}${NC}"
    echo -e "${CYAN}══════════════════════════════════════════════════════════${NC}"
    docker build -t "${IMAGE_NAME}" .
    echo -e "${GREEN}✓ Build complete${NC}"
    echo ""
fi

# ── Step 2: Ensure data directory ──────────────────────────────────────────
mkdir -p "${DATA_DIR}"
mkdir -p "${DATA_DIR}/config"
echo -e "${YELLOW}Data directory: ${DATA_DIR}${NC}"

# First launch: choose autonomous pipeline vs ideas-only (writes marker inside container)
FIRST_MARK="${DATA_DIR}/config/first_run_pipeline_mode.done"
if [[ ! -f "${FIRST_MARK}" ]] && [[ -t 0 ]] && [[ -z "${AIFACTORY_AUTONOMOUS_PIPELINE:-}" ]]; then
    echo ""
    echo "AI-Factory — pipeline mode (first run with this data directory)"
    echo "  1) Autonomous mode — Director periodically creates new products"
    echo "  2) Ideas only — new products only when you submit an idea"
    read -r -p "Choose [1/2], Enter = 2: " _mode_choice || true
    _mode_choice="${_mode_choice:-2}"
    case "${_mode_choice}" in
        1) export AIFACTORY_AUTONOMOUS_PIPELINE=1 ;;
        *) export AIFACTORY_AUTONOMOUS_PIPELINE=0 ;;
    esac
fi
echo ""

# ── Step 3: Stop & remove old container ────────────────────────────────────
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${YELLOW}Stopping and removing existing container '${CONTAINER_NAME}'...${NC}"
    docker stop "${CONTAINER_NAME}" 2>/dev/null || true
    docker rm "${CONTAINER_NAME}" 2>/dev/null || true
    echo -e "${GREEN}✓ Old container removed${NC}"
    echo ""
fi

# ── Step 4: Run container ──────────────────────────────────────────────────
echo -e "${CYAN}══════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Starting AI-Factory container${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  Frontend:  ${GREEN}http://localhost:${FRONTEND_PORT}${NC}"
echo -e "  Backend:   ${GREEN}http://localhost:${BACKEND_PORT}/api/health${NC}"
echo -e "  Admin:     ${GREEN}http://localhost:${FRONTEND_PORT}/admin/login${NC}"
echo -e "  Data:      ${YELLOW}${DATA_DIR}${NC}"
echo ""

docker run -d \
    --name "${CONTAINER_NAME}" \
    --restart unless-stopped \
    -p "${FRONTEND_PORT}:8080" \
    -p "${BACKEND_PORT}:8081" \
    -v "${DATA_DIR}:/app/data" \
    --add-host host.docker.internal:host-gateway \
    -e "AIFACTORY_AUTONOMOUS_PIPELINE=${AIFACTORY_AUTONOMOUS_PIPELINE:-}" \
    -e "AIFACTORY_CONFIG_YAML=/app/data/config/admin_config_overlay.yaml" \
    -e "AIFACTORY_CONFIG_FRAGMENTS_DIR=/app/config/fragments" \
    ${JWT_SECRET_KEY+-e "JWT_SECRET_KEY=${JWT_SECRET_KEY}"} \
    ${DEEPSEEK_API_KEY+-e "DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}"} \
    ${TOGETHER_API_KEY+-e "TOGETHER_API_KEY=${TOGETHER_API_KEY}"} \
    ${GROQ_API_KEY+-e "GROQ_API_KEY=${GROQ_API_KEY}"} \
    "${IMAGE_NAME}"

echo ""
echo -e "${GREEN}✓ Container '${CONTAINER_NAME}' started successfully!${NC}"
echo ""

# ── Step 5: Show logs (first 10 lines) ─────────────────────────────────────
echo -e "${YELLOW}Waiting for services to initialize (10s)...${NC}"
sleep 10

echo -e "${CYAN}── Recent container logs ──${NC}"
docker logs --tail 10 "${CONTAINER_NAME}" 2>&1 || true

echo ""
echo -e "${CYAN}── Container status ──${NC}"
docker ps --filter "name=${CONTAINER_NAME}" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo -e "${GREEN}══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  AI-Factory is running!${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${CYAN}Frontend:${NC}   http://localhost:${FRONTEND_PORT}"
echo -e "  ${CYAN}Admin:${NC}      http://localhost:${FRONTEND_PORT}/admin/login"
echo -e "  ${CYAN}API Health:${NC} http://localhost:${BACKEND_PORT}/api/health"
echo -e "  ${CYAN}Categories:${NC} http://localhost:${BACKEND_PORT}/api/products/categories"
echo -e "  ${CYAN}Products:${NC}   http://localhost:${BACKEND_PORT}/api/products"
echo ""
echo -e "  ${YELLOW}Admin login:${NC} admin / demo123"
echo ""
echo -e "  ${YELLOW}To stop:${NC}  docker stop ${CONTAINER_NAME}"
echo -e "  ${YELLOW}To start:${NC} docker start ${CONTAINER_NAME}"
echo -e "  ${YELLOW}To rebuild:${NC} ./run.sh"
echo -e "  ${YELLOW}To view logs:${NC} docker logs -f ${CONTAINER_NAME}"
echo ""
