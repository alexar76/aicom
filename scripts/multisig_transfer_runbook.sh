#!/usr/bin/env bash
# KI-4 — Transfer EVM contract ownership to a Gnosis Safe (2-of-N).
#
# Prerequisites:
#   - Safe deployed at $SAFE_ADDR (https://app.safe.global)
#   - Deployer EOA with current owner role: $DEPLOYER
#   - cast (Foundry) + RPC: $BASE_RPC (default https://mainnet.base.org)
#
# Usage:
#   export SAFE_ADDR=0x...
#   export ESCROW_ADDR=0x3Df85a639EAB8B50DD14f09bdeB46D5FeF163017
#   export NFT_ADDR=0xA9Af496fD4A1Dc594029Aa8Ea2dbd236Fd255033
#   export DEPLOYER=0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a
#   export BASE_RPC=https://mainnet.base.org
#   ./scripts/multisig_transfer_runbook.sh dry-run
#   ./scripts/multisig_transfer_runbook.sh broadcast
#
# After broadcast: accept ownership FROM THE SAFE UI for each contract.

set -euo pipefail

MODE="${1:-dry-run}"
BASE_RPC="${BASE_RPC:-https://mainnet.base.org}"
SAFE_ADDR="${SAFE_ADDR:-}"
ESCROW_ADDR="${ESCROW_ADDR:-0x3Df85a639EAB8B50DD14f09bdeB46D5FeF163017}"
NFT_ADDR="${NFT_ADDR:-0xA9Af496fD4A1Dc594029Aa8Ea2dbd236Fd255033}"
DEPLOYER="${DEPLOYER:-}"

if [[ -z "$SAFE_ADDR" ]]; then
  echo "Set SAFE_ADDR to your Gnosis Safe address." >&2
  exit 2
fi

if ! command -v cast >/dev/null 2>&1; then
  echo "Install Foundry (cast) first: https://book.getfoundry.sh" >&2
  exit 2
fi

echo "=== KI-4 multisig transfer runbook ==="
echo "Safe:   $SAFE_ADDR"
echo "Escrow: $ESCROW_ADDR"
echo "NFT:    $NFT_ADDR"
echo "RPC:    $BASE_RPC"
echo ""

for label addr in Escrow "$ESCROW_ADDR" NFT "$NFT_ADDR"; do
  owner=$(cast call "$addr" "owner()(address)" --rpc-url "$BASE_RPC" 2>/dev/null || echo "unknown")
  pending=$(cast call "$addr" "pendingOwner()(address)" --rpc-url "$BASE_RPC" 2>/dev/null || echo "unknown")
  echo "$label owner:         $owner"
  echo "$label pendingOwner:  $pending"
done

echo ""
echo "Step 1 — deployer calls transferOwnership(Safe) on each contract"
echo "Step 2 — Safe owners call acceptOwnership() on each contract"
echo ""

if [[ "$MODE" == "dry-run" ]]; then
  echo "[dry-run] Would run:"
  echo "  cast send $ESCROW_ADDR \"transferOwnership(address)\" $SAFE_ADDR --rpc-url $BASE_RPC --from $DEPLOYER"
  echo "  cast send $NFT_ADDR \"transferOwnership(address)\" $SAFE_ADDR --rpc-url $BASE_RPC --from $DEPLOYER"
  echo ""
  echo "Re-run with: $0 broadcast"
  exit 0
fi

if [[ "$MODE" != "broadcast" ]]; then
  echo "Usage: $0 dry-run|broadcast" >&2
  exit 2
fi

if [[ -z "$DEPLOYER" ]]; then
  echo "Set DEPLOYER for broadcast mode." >&2
  exit 2
fi

read -r -p "Broadcast transferOwnership to Safe $SAFE_ADDR? [y/N] " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
  echo "Aborted."
  exit 1
fi

cast send "$ESCROW_ADDR" "transferOwnership(address)" "$SAFE_ADDR" --rpc-url "$BASE_RPC" --from "$DEPLOYER"
cast send "$NFT_ADDR" "transferOwnership(address)" "$SAFE_ADDR" --rpc-url "$BASE_RPC" --from "$DEPLOYER"

echo ""
echo "Done. Now accept ownership from the Safe UI for both contracts."
echo "Verify: cast call $ESCROW_ADDR 'owner()(address)' --rpc-url $BASE_RPC"
