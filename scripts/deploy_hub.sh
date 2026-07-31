#!/usr/bin/env bash
# Build AIMarket Hub from monorepo root and (re)start modelmarket-hub on :9083.
#
# Full fleet: ./scripts/deploy_ecosystem.sh (step 2). Do NOT redeploy via aimarket-hub/docker compose.
# See: docs/deploy-ecosystem.md
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HUB_PORT="${AIMARKET_HUB_HOST_PORT:-9083}"
TAG="$("$ROOT/scripts/docker_image_tag.sh")"
IMAGE="${AIMARKET_HUB_IMAGE:-modelmarket-hub:${TAG}}"
VOLUME="${AIMARKET_HUB_VOLUME:-modelmarket_hub_data}"
HUB_NAME="${AIMARKET_HUB_NAME:-modelmarket.dev}"
HUB_URL="${AIMARKET_HUB_URL:-https://modelmarket.dev}"
SEED_LIST="${AIMARKET_SEED_LIST:-https://magic-ai-factory.com/.well-known/ai-market.json,https://oracles.modelmarket.dev/.well-known/ai-market.json}"
FACTORY_URL="${AIFACTORY_PUBLIC_URL:-https://magic-ai-factory.com}"

ADMIN_TOKEN="${AIMARKET_ADMIN_TOKEN:-}"
if [[ -z "$ADMIN_TOKEN" && -f "$ROOT/data/secrets/aimarket_admin_token.txt" ]]; then
  ADMIN_TOKEN="$(tr -d '[:space:]' < "$ROOT/data/secrets/aimarket_admin_token.txt")"
fi
if [[ -z "$ADMIN_TOKEN" ]]; then
  ADMIN_TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  mkdir -p "$ROOT/data/secrets"
  printf '%s\n' "$ADMIN_TOKEN" > "$ROOT/data/secrets/aimarket_admin_token.txt"
  chmod 600 "$ROOT/data/secrets/aimarket_admin_token.txt"
  echo "Generated AIMARKET_ADMIN_TOKEN → data/secrets/aimarket_admin_token.txt"
fi

echo "=== AIMarket Hub deploy ==="
echo "Build context: $ROOT (dockerfile aimarket-hub/Dockerfile)"

docker build -f "$ROOT/aimarket-hub/Dockerfile" -t "$IMAGE" "$ROOT"

docker rm -f modelmarket-hub 2>/dev/null || true
ENV_FILE="$ROOT/.env"
DOCKER_ENV=()
if [[ -f "$ENV_FILE" ]]; then
  DOCKER_ENV+=(--env-file "$ENV_FILE")
fi
FACTORY_DATA="${AIFACTORY_DATA_ROOT:-$ROOT/data}"

docker run -d --name modelmarket-hub --restart unless-stopped \
  --add-host=host.docker.internal:host-gateway \
  "${DOCKER_ENV[@]}" \
  -p "127.0.0.1:${HUB_PORT}:9083" \
  -v "${VOLUME}:/app/data" \
  -v "${FACTORY_DATA}:/factory_data:ro" \
  -e AIMARKET_HUB_NAME="${HUB_NAME}" \
  -e AIMARKET_HUB_URL="${HUB_URL}" \
  -e AIMARKET_SEED_LIST="${SEED_LIST}" \
  -e AIMARKET_ADMIN_TOKEN="${ADMIN_TOKEN}" \
  -e AIFACTORY_PUBLIC_URL="${FACTORY_URL}" \
  -e AIFACTORY_DATA_ROOT=/factory_data \
  -e AIMARKET_DB_PATH=/app/data/hub.db \
  -e AIMARKET_SIGNING_KEY_PATH=/app/data/hub_signing_key \
  -e AIMARKET_INVOKE_HOST_GATEWAY="${AIMARKET_INVOKE_HOST_GATEWAY:-host.docker.internal}" \
  "$IMAGE"

echo "Waiting for Hub health..."
for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${HUB_PORT}/.well-known/ai-market.json" >/dev/null; then
    curl -sf "http://127.0.0.1:${HUB_PORT}/.well-known/ai-market.json" | head -c 120
    echo ""
    echo "Hub OK: http://127.0.0.1:${HUB_PORT}"
    echo "--- Syncing factory catalog into hub volume ---"
    PYTHONPATH="$ROOT:$ROOT/aimarket-hub" AIFACTORY_DATA_ROOT="$FACTORY_DATA" \
      python3 "$ROOT/scripts/sync_pipeline_mirror_and_hub.py" --mirror-only \
      || echo "WARN: pipeline mirror failed — hub may serve stale catalog"
    docker exec -e AIFACTORY_DATA_ROOT=/factory_data modelmarket-hub python3 - <<'PY' || echo "WARN: hub import failed"
from pathlib import Path
from aimarket_hub.database import HubDatabase
from aimarket_hub.factory_bridge import import_factory_products

db = HubDatabase("/app/data/hub.db")
p = Path("/factory_data/pipeline.json")
if not p.is_file():
    p = Path("/factory_data/state/pipeline.json")
total = import_factory_products(db, pipeline_json_path=str(p))
print(f"import_factory_products upserted {total} capability row(s)")
PY
    docker exec modelmarket-hub python3 - <<'PY' || echo "WARN: oracle-family federated sync failed"
import asyncio, os, sys
sys.path.insert(0, "/app/aimarket-hub")
os.environ.setdefault("AIMARKET_DB_PATH", "/app/data/hub.db")

async def main():
    from aimarket_hub.config import HubConfig
    from aimarket_hub.crawler import Crawler
    from aimarket_hub.database import HubDatabase
    from aimarket_hub.signing import Signer
    from aimarket_hub.trust import TrustScorer
    wk = os.environ.get("ORACLE_FAMILY_WELL_KNOWN", "https://oracles.modelmarket.dev/.well-known/ai-market.json")
    config = HubConfig()
    db = HubDatabase(config.db_path, database_url=config.database_url)
    signer = Signer(config.signing_key_path)
    crawler = Crawler(config=config, db=db, signer=signer, trust_scorer=TrustScorer(db))
    try:
        result = await crawler._crawl_one(wk, 0, "deploy_hub")
        sortes = db.find_by_capability_id("sortes.draw@v1")
        print(f"oracle-family indexed={result.get('capabilities_count') if result else 0} sortes={sortes is not None}")
    finally:
        await crawler.close()
        db.close()

asyncio.run(main())
PY
    exit 0
  fi
  sleep 2
done

echo "ERROR: Hub not healthy on :${HUB_PORT}" >&2
docker logs modelmarket-hub --tail 40
exit 1
