#!/usr/bin/env bash
# Register Platon (oracles.modelmarket.dev) with the local AIMarket Hub federation.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HUB_PORT="${AIMARKET_HUB_HOST_PORT:-9083}"
DOMAIN="${PLATON_PUBLIC_DOMAIN:-oracles.modelmarket.dev}"
PLATON_PUBKEY="${PLATON_SIGNER_PUBLIC_KEY:-+UWIwNJV6W5S8yMfWRsPz9MYhun90pcaeFiI6eRA5Jc=}"

ADMIN_TOKEN="${AIMARKET_ADMIN_TOKEN:-}"
if [[ -z "$ADMIN_TOKEN" && -f "$ROOT/data/secrets/aimarket_admin_token.txt" ]]; then
  ADMIN_TOKEN="$(tr -d '[:space:]' < "$ROOT/data/secrets/aimarket_admin_token.txt")"
fi
if [[ -z "$ADMIN_TOKEN" ]]; then
  echo "Missing AIMARKET_ADMIN_TOKEN (data/secrets/aimarket_admin_token.txt)" >&2
  exit 1
fi

BASE="https://${DOMAIN}"
WELL_KNOWN="${BASE}/.well-known/ai-market.json"

echo "Checking ${WELL_KNOWN} ..."
CAPS="$(curl -sf "${WELL_KNOWN}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("capabilities_count", 0))')"
echo "Platon capabilities_count=${CAPS}"

echo "Announcing to hub :${HUB_PORT} ..."
curl -sf -X POST "http://127.0.0.1:${HUB_PORT}/ai-market/v2/federation/announce" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"hub_url\":\"${BASE}\",\"well_known_url\":\"${WELL_KNOWN}\",\"hub_name\":\"Platon Shadow Oracle\",\"capabilities_count\":${CAPS},\"signer_public_key\":\"${PLATON_PUBKEY}\"}"
echo ""

echo "Triggering crawl ..."
curl -sf -X POST "http://127.0.0.1:${HUB_PORT}/ai-market/v2/federation/crawl" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"force":true}'
echo ""

echo "Peers:"
curl -sf "http://127.0.0.1:${HUB_PORT}/ai-market/v2/federation/peers" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" | python3 -m json.tool 2>/dev/null | head -40
