#!/usr/bin/env bash
# Deploy acex-capital to Solana (devnet | mainnet).
# Private key read from console — never persisted (same pattern as contracts/solana/deploy.sh).
#
# Usage:
#   cd acex/contracts/solana
#   ./deploy.sh devnet
#   ./deploy.sh mainnet
#
set -euo pipefail

NETWORK="${1:-}"
if [[ -z "$NETWORK" ]]; then
  echo "Usage: $0 devnet|mainnet"
  exit 1
fi

case "$NETWORK" in
  devnet) RPC="${SOLANA_RPC_DEVNET:-https://api.devnet.solana.com}" ;;
  mainnet) RPC="${SOLANA_RPC_MAINNET:-https://api.mainnet-beta.solana.com}" ;;
  *) echo "Unknown network: $NETWORK"; exit 1 ;;
esac

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  ACEX Capital (Solana) — Deploy to ${NETWORK}"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

if [[ -t 0 ]]; then
  read -s -p "Deployer private key (JSON array or base58): " RAW_KEY
  echo ""
else
  read -r RAW_KEY
fi

[[ -n "$RAW_KEY" ]] || { echo "No key provided"; exit 1; }

TMP_KEYFILE=$(mktemp)
chmod 600 "$TMP_KEYFILE"
if [[ "$RAW_KEY" == \[* ]]; then
  echo "$RAW_KEY" > "$TMP_KEYFILE"
else
  python3 -c "
import json, base58
print(json.dumps(list(base58.b58decode('$RAW_KEY'))))
" > "$TMP_KEYFILE"
fi
RAW_KEY="REDACTED"

PUBKEY=$(solana-keygen pubkey "$TMP_KEYFILE" 2>/dev/null || echo "unknown")
echo "Deployer: $PUBKEY"
read -p "Continue? (y/N) " CONFIRM
[[ "$CONFIRM" == "y" || "$CONFIRM" == "Y" ]] || { rm -f "$TMP_KEYFILE"; exit 0; }

anchor build 2>&1 || { rm -f "$TMP_KEYFILE"; exit 1; }

solana program deploy \
  --url "$RPC" \
  --keypair "$TMP_KEYFILE" \
  target/deploy/acex_capital.so \
  ${DEPLOY_ARGS:-}

EXIT=$?
rm -f "$TMP_KEYFILE"

if [[ $EXIT -eq 0 ]]; then
  echo "=== ACEX Capital deployed ==="
  echo "Program ID: AcexCap1italMark3tL1st1ngReg1stryPDA"
  echo "Next: anchor run initialize (or hub admin tx)"
else
  echo "=== Deploy failed ($EXIT) ==="
fi
exit $EXIT
