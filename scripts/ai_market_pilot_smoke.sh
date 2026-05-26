#!/usr/bin/env bash
set -euo pipefail

# AI-market production pilot smoke checklist (5 requests):
# 1) pilot config
# 2) catalog list
# 3) settlement confirm (real tx)
# 4) entitlement lookup
# 5) capability invoke (licensed)
#
# Usage:
#   BASE_URL=http://127.0.0.1:8081 \
#   PRODUCT_ID=prod-xxxx \
#   TX_HASH=0x... \
#   CHAIN=base TOKEN=USDT CONTRACT_ADDRESS=0x... \
#   CUSTOMER_ID=aimkt-smoke CUSTOMER_EMAIL=smoke@example.com \
#   WALLET_ADDRESS=0xBuyerWallet AMOUNT=1.0 \
#   CAPABILITY_ID=generate_report \
#   ./scripts/ai_market_pilot_smoke.sh

BASE_URL="${BASE_URL:-http://127.0.0.1:8081}"
PRODUCT_ID="${PRODUCT_ID:-}"
TX_HASH="${TX_HASH:-}"
CHAIN="${CHAIN:-base}"
TOKEN="${TOKEN:-USDT}"
CONTRACT_ADDRESS="${CONTRACT_ADDRESS:-}"
CUSTOMER_ID="${CUSTOMER_ID:-aimkt-smoke}"
CUSTOMER_EMAIL="${CUSTOMER_EMAIL:-smoke@example.com}"
WALLET_ADDRESS="${WALLET_ADDRESS:-}"
AMOUNT="${AMOUNT:-1.0}"
CAPABILITY_ID="${CAPABILITY_ID:-health_check}"

echo "1) GET /ai-market/pilot/config"
curl -sS "${BASE_URL}/ai-market/pilot/config" | python3 -m json.tool

echo "2) GET /ai-market/products"
curl -sS "${BASE_URL}/ai-market/products" | python3 -m json.tool

if [[ -z "${PRODUCT_ID}" || -z "${TX_HASH}" ]]; then
  echo "STOP: set PRODUCT_ID and TX_HASH for steps 3-5."
  exit 1
fi

echo "3) POST /ai-market/pilot/settlement/confirm"
SETTLEMENT_JSON="$(curl -sS -X POST "${BASE_URL}/ai-market/pilot/settlement/confirm" \
  -H "Content-Type: application/json" \
  -d "{
    \"product_id\": \"${PRODUCT_ID}\",
    \"tx_hash\": \"${TX_HASH}\",
    \"chain\": \"${CHAIN}\",
    \"token\": \"${TOKEN}\",
    \"contract_address\": \"${CONTRACT_ADDRESS}\",
    \"customer_id\": \"${CUSTOMER_ID}\",
    \"customer_email\": \"${CUSTOMER_EMAIL}\",
    \"wallet_address\": \"${WALLET_ADDRESS}\"
  }")"
echo "${SETTLEMENT_JSON}" | python3 -m json.tool
LICENSE_KEY="$(echo "${SETTLEMENT_JSON}" | python3 -c 'import json,sys;print((json.load(sys.stdin).get("license_key") or "").strip())')"

echo "4) GET /ai-market/entitlements/${CUSTOMER_ID}"
curl -sS "${BASE_URL}/ai-market/entitlements/${CUSTOMER_ID}" | python3 -m json.tool

if [[ -z "${LICENSE_KEY}" ]]; then
  echo "STOP: no license_key from settlement confirm."
  exit 1
fi

echo "5) POST /ai-market/capabilities/${PRODUCT_ID}/${CAPABILITY_ID}/invoke"
curl -sS -X POST "${BASE_URL}/ai-market/capabilities/${PRODUCT_ID}/${CAPABILITY_ID}/invoke" \
  -H "Content-Type: application/json" \
  -H "x-ai-market-license: ${LICENSE_KEY}" \
  -d '{"smoke": true, "timestamp": "manual"}' | python3 -m json.tool

echo "Smoke flow completed."
