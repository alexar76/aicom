#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export AIMARKET_SKIP_DEMO_SEED=1
export MESH_ENV=production
export MESH_ALLOW_INSECURE_TOKENS=1
export MESH_HUB_URL=http://127.0.0.1:9080
export MESH_SKIP_DEMO_CAPABILITIES=true
export MESH_REJECT_DEMO_INVOKE_OUTPUT=true
export MESH_ALLOW_LOCALHOST_AGENTS=true
export MESH_API_TOKEN="${MESH_API_TOKEN:-mesh-local-api}"
export MESH_ADMIN_TOKEN="${MESH_ADMIN_TOKEN:-mesh-local-admin}"
export MESH_CORS_ORIGINS=http://localhost:5173
export MESH_DATA_DIR="$ROOT/backend/.mesh_data"
export MESH_REAL_AGENT_URL=http://127.0.0.1:8091
export MESH_API_URL=http://127.0.0.1:8090

cleanup() {
  [[ -n "${HUB_PID:-}" ]] && kill "$HUB_PID" 2>/dev/null || true
  [[ -n "${MESH_PID:-}" ]] && kill "$MESH_PID" 2>/dev/null || true
  [[ -n "${AGENT_PID:-}" ]] && kill "$AGENT_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "==> Starting real agent (:8091)"
python3 scripts/real_agent_server.py &
AGENT_PID=$!
sleep 1

echo "==> Starting AIMarket Hub (:9080, no demo seed)"
(cd "$ROOT/../aimarket-hub" && PYTHONPATH=. .venv/bin/python -m aimarket_hub.cli serve) &
HUB_PID=$!
for i in $(seq 1 40); do
  curl -sf http://127.0.0.1:9080/.well-known/ai-market.json >/dev/null && break
  sleep 0.5
done

echo "==> Starting Mesh API (:8090)"
(cd "$ROOT/backend" && PYTHONPATH=. .venv/bin/python -m ai_service_mesh.main) &
MESH_PID=$!
for i in $(seq 1 40); do
  curl -sf http://127.0.0.1:8090/health >/dev/null && break
  sleep 0.5
done

echo "==> Unit tests"
(cd "$ROOT/backend" && PYTHONPATH=. .venv/bin/pytest -q tests/test_security.py tests/test_api.py tests/test_orchestrator.py)

echo "==> Integration tests (real HTTP)"
sleep 2
(cd "$ROOT/backend" && PYTHONPATH=. .venv/bin/pytest -q -m integration tests/test_integration_e2e.py)

echo "==> Hub search (expect empty or no non-demo without factory)"
curl -s "http://127.0.0.1:9080/ai-market/v2/search?intent=research&budget=5&limit=3" | python3 -m json.tool | head -20

echo "==> Register verified local agent"
python3 scripts/register_e2e_agent.py | head -12

echo "==> Real-agent mesh task"
curl -s -X POST http://127.0.0.1:8090/v1/tasks \
  -H "Authorization: Bearer $MESH_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"intent":"research agent mesh","budget_usd":3,"preferred_capabilities":["research"]}' \
  | python3 -m json.tool | head -35

echo "OK: infra test complete"
