#!/usr/bin/env bash
# Build and start AI Service Mesh API on 127.0.0.1:8090 (uses existing Hub on :9083).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MESH="$ROOT/ai-service-mesh"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"

echo "=== AI Service Mesh deploy ==="

if [[ ! -d "$MESH" ]]; then
  echo "ERROR: $MESH not found" >&2
  exit 1
fi

# Ensure mesh tokens exist in .env
python3 <<PY
import secrets
from pathlib import Path

env = Path("$ENV_FILE")
text = env.read_text(encoding="utf-8") if env.is_file() else ""
def _has_val(prefix: str) -> bool:
    for ln in text.splitlines():
        if ln.startswith(prefix) and len(ln.strip()) > len(prefix) + 8:
            return True
    return False

lines = text.splitlines()
added = []
if not _has_val("MESH_API_TOKEN="):
    lines = [ln for ln in lines if not ln.startswith("MESH_API_TOKEN=")]
    lines.append(f"MESH_API_TOKEN=mesh-prod-{secrets.token_urlsafe(24)}")
    added.append("MESH_API_TOKEN")
if not _has_val("MESH_ADMIN_TOKEN="):
    lines = [ln for ln in lines if not ln.startswith("MESH_ADMIN_TOKEN=")]
    lines.append(f"MESH_ADMIN_TOKEN=mesh-admin-{secrets.token_urlsafe(24)}")
    added.append("MESH_ADMIN_TOKEN")
if not _has_val("MESH_HUB_URL="):
    lines.append("MESH_HUB_URL=http://127.0.0.1:9083")
    added.append("MESH_HUB_URL")
if not _has_val("MESH_PUBLIC_READ="):
    lines.append("MESH_PUBLIC_READ=0")
    added.append("MESH_PUBLIC_READ=0")
if not _has_val("ALIEN_MODE="):
    lines.append("ALIEN_MODE=real")
    added.append("ALIEN_MODE=real")
elif any(ln.strip() == "ALIEN_MODE=test" for ln in text.splitlines()):
    lines = [ln for ln in lines if not ln.startswith("ALIEN_MODE=")]
    lines.append("ALIEN_MODE=real")
    added.append("ALIEN_MODE=real (was test)")
env.write_text("\n".join(lines) + "\n", encoding="utf-8")
if added:
    print("Added to .env:", ", ".join(added))
else:
    print(".env already has MESH_* keys")
PY

cd "$MESH"
export AICOM_IMAGE_TAG="${AICOM_IMAGE_TAG:-$("$ROOT/scripts/docker_image_tag.sh")}"
echo "Docker image tag: $AICOM_IMAGE_TAG"
docker compose -f docker-compose.prod.yml build --pull
docker compose -f docker-compose.prod.yml up -d --force-recreate

echo "Waiting for Mesh health..."
for _ in $(seq 1 40); do
  if curl -sf "http://127.0.0.1:8090/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
curl -sf "http://127.0.0.1:8090/health" | head -c 300 || {
  echo "ERROR: Mesh not healthy on :8090" >&2
  docker compose -f docker-compose.prod.yml logs --tail=50
  exit 1
}
echo ""
echo "Mesh API: http://127.0.0.1:8090"
echo "Stats:    http://127.0.0.1:8090/v1/stats"
