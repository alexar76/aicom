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
# The seed list lives in aimarket-hub/aimarket_hub/federation_seeds.json and NOWHERE ELSE.
# This variable REPLACES that file when set, and the default it used to carry named four of
# the six seeds committed there — so a deployment crawled the four and the operator-vouched
# pins for the rest never took effect. "Keep in sync" is not a mechanism; one source is.
# Set AIMARKET_SEED_LIST only to deploy a hub with a deliberately different federation.
SEED_LIST="${AIMARKET_SEED_LIST:-}"
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

ZK_WASM="$ROOT/contracts/zk/build/input_validity_js/input_validity.wasm"
ZK_ZKEY="$ROOT/contracts/zk/build/input_validity_plonk.zkey"
if [[ ! -f "$ZK_WASM" || ! -f "$ZK_ZKEY" ]]; then
  echo "→ PLONK artifacts missing — running contracts/zk/scripts/setup_plonk.sh"
  bash "$ROOT/contracts/zk/scripts/setup_plonk.sh"
fi

docker build -f "$ROOT/aimarket-hub/Dockerfile" -t "$IMAGE" "$ROOT"

docker rm -f modelmarket-hub 2>/dev/null || true
ENV_FILE="$ROOT/.env"
# Hub-only payment interlock (see deploy/hub-payment.env.example). Loaded AFTER shared
# .env so addresses/flags win. Without this file, redeploys silently leave payments off
# (payment_configured=false) — that is how the 2026-07-31 image wiped the July-27 enable.
PAYMENT_ENV="${AIMARKET_HUB_PAYMENT_ENV:-$ROOT/deploy/hub-payment.env}"
ZK_ENV="${AIMARKET_HUB_ZK_ENV:-$ROOT/deploy/hub-zk.env}"
# Host-only secrets (gitignored). A monorepo `rsync --delete` can wipe them from $ROOT/deploy/
# while durable copies outside the tree survive — restore before we warn-and-boot unpaid.
if [[ ! -f "$PAYMENT_ENV" ]]; then
  for _pay_backup in \
    "${AIMARKET_HUB_PAYMENT_ENV_BACKUP:-/root/deploy/hub-payment.env}" \
    /root/aicom-hub-build/deploy/hub-payment.env
  do
    if [[ -f "$_pay_backup" ]]; then
      mkdir -p "$(dirname "$PAYMENT_ENV")"
      install -m 600 "$_pay_backup" "$PAYMENT_ENV"
      echo "Restored payment env from $_pay_backup → $PAYMENT_ENV"
      break
    fi
  done
fi
if [[ ! -f "$ZK_ENV" ]]; then
  for _zk_backup in \
    "${AIMARKET_HUB_ZK_ENV_BACKUP:-/root/deploy/hub-zk.env}" \
    /root/aicom-hub-build/deploy/hub-zk.env
  do
    if [[ -f "$_zk_backup" ]]; then
      mkdir -p "$(dirname "$ZK_ENV")"
      install -m 600 "$_zk_backup" "$ZK_ENV"
      echo "Restored ZK env from $_zk_backup → $ZK_ENV"
      break
    fi
  done
fi
DOCKER_ENV=()
if [[ -f "$ENV_FILE" ]]; then
  DOCKER_ENV+=(--env-file "$ENV_FILE")
fi
if [[ -f "$PAYMENT_ENV" ]]; then
  DOCKER_ENV+=(--env-file "$PAYMENT_ENV")
  echo "Payment env: $PAYMENT_ENV"
else
  echo "WARN: no $PAYMENT_ENV — hub will start without payment interlock" >&2
  echo "      (copy deploy/hub-payment.env.example → deploy/hub-payment.env on the host)" >&2
  echo "      Keep a durable copy at /root/deploy/hub-payment.env (outside the monorepo tree)." >&2
fi
if [[ -f "$ZK_ENV" ]]; then
  DOCKER_ENV+=(--env-file "$ZK_ENV")
  echo "ZK env: $ZK_ENV"
else
  echo "WARN: no $ZK_ENV — real PLONK disabled; ZK plugin uses labeled HTTP demo fallback" >&2
  echo "      (copy deploy/hub-zk.env.example → deploy/hub-zk.env on the host)" >&2
fi
FACTORY_DATA="${AIFACTORY_DATA_ROOT:-$ROOT/data}"

docker run -d --name modelmarket-hub --restart unless-stopped \
  --add-host=host.docker.internal:host-gateway \
  --network aicom_aicom_net \
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

# Also attach default bridge so host.docker.internal gateway paths keep working for
# outbound invokes that resolve host ports (compose network alone can break some paths).
docker network connect bridge modelmarket-hub 2>/dev/null || true

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
    # The /family aggregate, not the bare host: this step asserts `sortes.draw@v1` was indexed,
    # and sortes is one of the sixteen oracles that only the family manifest carries. Pointed at
    # oracles.modelmarket.dev (Platon alone) the assertion could never pass, and printed
    # `sortes=False` beside a non-zero indexed count for a month without failing the deploy.
    wk = os.environ.get("ORACLE_FAMILY_WELL_KNOWN", "https://oracles.modelmarket.dev/family/.well-known/ai-market.json")
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
    echo "--- Verifying advertised federation URLs ---"
    # A hub can be healthy, crawl on schedule and still serve an empty catalogue: every
    # 2026-07-31 cause (factory advertising http://localhost:9080, the oracle advertising
    # http://<raw-ip> with a 404 manifest, a seed pinned to the wrong signer) answers 200 to
    # every check a health probe makes. Non-fatal: the hub is up and rolling back would not
    # fix a peer's env, but the deploy must not exit 0 while the storefront is empty.
    if AIMARKET_SEED_LIST="${SEED_LIST}" AIMARKET_HUB_URL="${HUB_URL}" \
        python3 "$ROOT/scripts/verify_federation_urls.py" --hub "http://127.0.0.1:${HUB_PORT}"; then
      echo "Federation URLs OK"
      exit 0
    fi
    echo "WARN: federation URL check failed — the hub is up, but at least one advertised URL" >&2
    echo "      or seed is wrong, so part of the catalogue will stay empty (details above)." >&2
    exit 2
  fi
  sleep 2
done

echo "ERROR: Hub not healthy on :${HUB_PORT}" >&2
docker logs modelmarket-hub --tail 40
exit 1
