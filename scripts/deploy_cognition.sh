#!/usr/bin/env bash
# Deploy DIOSCURI + HELIOS + worker on a shared cognition volume (admin-vps).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ECO_DATA="${ECOSYSTEM_DATA_DIR:-/root/ecosystem-data}"
VOLUME_NAME="${COGNITION_VOLUME:-aicom-ecosystem-data}"
COMPOSE_BIND=(-f docs/ecosystem/docker-compose.cognition.bind.yml)

echo "=== Cognition deploy (shared data: ${ECO_DATA}) ==="

mkdir -p "${ECO_DATA}"
export ECOSYSTEM_DATA_DIR="${ECO_DATA}"

# Bind host dir when not using named volume mount helper
if command -v setfacl >/dev/null 2>&1; then
  setfacl -R -m u:1000:rwx -m u:10001:rwx "${ECO_DATA}" || true
  setfacl -R -d -m u:1000:rwx -m u:10001:rwx "${ECO_DATA}" || true
else
  chmod -R a+rwX "${ECO_DATA}" || true
fi

cd "${ROOT}"
export HELIOS_SYNDICATION="${HELIOS_SYNDICATION:-1}"
export HELIOS_QUEUE_PATH="${HELIOS_QUEUE_PATH:-/data/helios-queue.jsonl}"

docker compose \
  -f dioscuri/docker-compose.yml \
  -f helios/docker-compose.yml \
  -f docs/ecosystem/docker-compose.cognition.yml \
  "${COMPOSE_BIND[@]}" \
  up -d --build dioscuri helios helios-worker

sleep 4
curl -sf "http://127.0.0.1:${DIOSCURI_PORT:-8790}/health" | head -c 120 || true
echo
curl -sf "http://127.0.0.1:${HELIOS_PORT:-8791}/health" | head -c 120 || true
echo
docker ps --format '{{.Names}} {{.Status}}' | grep -E 'helios|dioscuri' || true
echo "Cognition OK"
