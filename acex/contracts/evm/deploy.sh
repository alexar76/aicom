#!/usr/bin/env bash
# Deploy ACEX EVM contracts (Base / Ethereum via Foundry).
#
# Usage:
#   export USDC_ADDRESS=0x...
#   export DEPLOYER_PRIVATE_KEY=0x...
#   export RPC_BASE_SEPOLIA=https://sepolia.base.org
#   ./deploy.sh base-sepolia
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

NETWORK="${1:-}"
case "$NETWORK" in
  base-sepolia) RPC="${RPC_BASE_SEPOLIA:?set RPC_BASE_SEPOLIA}" ;;
  base) RPC="${RPC_BASE_MAINNET:?set RPC_BASE_MAINNET}" ;;
  *)
    echo "Usage: $0 base-sepolia|base"
    exit 1
    ;;
esac

if [[ -z "${USDC_ADDRESS:-}" || -z "${DEPLOYER_PRIVATE_KEY:-}" ]]; then
  echo "Set USDC_ADDRESS and DEPLOYER_PRIVATE_KEY"
  exit 1
fi

if [[ ! -d lib/forge-std ]]; then
  forge install foundry-rs/forge-std OpenZeppelin/openzeppelin-contracts --no-commit
fi

forge build
VERIFY_ARGS=()
if [[ -n "${ETHERSCAN_API_KEY:-}" ]]; then
  VERIFY_ARGS=(--verify --etherscan-api-key "$ETHERSCAN_API_KEY")
fi

forge script script/DeployACEX.s.sol \
  --rpc-url "$RPC" \
  --broadcast \
  "${VERIFY_ARGS[@]}"

echo "Deploy complete. Save addresses from broadcast log."
