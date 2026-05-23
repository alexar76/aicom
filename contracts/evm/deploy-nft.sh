#!/usr/bin/env bash
# Deploy AIMarketCapabilityNFT (ERC-721 entitlements) to an EVM chain.
# Private key is read from console (no echo) and NEVER persisted.
#
# Usage:
#   cd contracts/evm
#   ./deploy-nft.sh base          # Base mainnet
#   ./deploy-nft.sh base-sepolia  # Base Sepolia testnet
#   ./deploy-nft.sh ethereum      # Ethereum mainnet
#   ./deploy-nft.sh arbitrum      # Arbitrum One
#
# Optional env:
#   INITIAL_HUBS=0xHUB1,0xHUB2    # comma-separated, addresses authorized to call consumeCall
#                                  # (default: just the deployer)
#
# What happens:
#   - You paste the private key at the prompt (input hidden)
#   - Foundry deploys AIMarketCapabilityNFT
#   - Deployer becomes the contract owner (only owner can mint and authorize hubs)
#   - Initial hubs are authorized to call consumeCall
#   - Key cleared from env immediately after

set -euo pipefail

CHAIN="${1:-}"
if [ -z "$CHAIN" ]; then
    echo "Usage: $0 <chain>"
    echo "  base | base-sepolia | ethereum | arbitrum"
    exit 1
fi

case "$CHAIN" in
    base)
        RPC_URL="${RPC_BASE_MAINNET:-https://mainnet.base.org}"
        VERIFIER_URL="https://api.basescan.org/api"
        ETHERSCAN_API_KEY="${BASESCAN_API_KEY:-}"
        ;;
    base-sepolia)
        RPC_URL="${RPC_BASE_SEPOLIA:-https://sepolia.base.org}"
        VERIFIER_URL="https://api-sepolia.basescan.org/api"
        ETHERSCAN_API_KEY="${BASESCAN_API_KEY:-}"
        ;;
    ethereum)
        RPC_URL="${RPC_ETHEREUM:-https://eth.llamarpc.com}"
        VERIFIER_URL="https://api.etherscan.io/api"
        ETHERSCAN_API_KEY="${ETHERSCAN_API_KEY:-}"
        ;;
    arbitrum)
        RPC_URL="${RPC_ARBITRUM:-https://arb1.arbitrum.io/rpc}"
        VERIFIER_URL="https://api.arbiscan.io/api"
        ETHERSCAN_API_KEY="${ARBISCAN_API_KEY:-}"
        ;;
    *)
        echo "Unknown chain: $CHAIN"
        exit 1
        ;;
esac

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  AIMarketCapabilityNFT — Deploy to ${CHAIN}"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Paste the deployer private key (input hidden):             ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

if [ -t 0 ]; then
    read -s -p "Private key (0x...): " DEPLOYER_PRIVATE_KEY
    echo ""
else
    read -r DEPLOYER_PRIVATE_KEY
fi

if [ -z "$DEPLOYER_PRIVATE_KEY" ]; then
    echo "ERROR: No private key provided."
    exit 1
fi

if [[ ! "$DEPLOYER_PRIVATE_KEY" =~ ^(0x)?[0-9a-fA-F]{64}$ ]]; then
    echo "ERROR: Private key must be 64 hex characters (with optional 0x prefix)."
    DEPLOYER_PRIVATE_KEY="REDACTED"
    exit 1
fi

PRIVATE_KEY="${DEPLOYER_PRIVATE_KEY#0x}"
DEPLOYER_ADDR=$(cast wallet address "0x${PRIVATE_KEY}")

echo ""
echo "Deployer address: ${DEPLOYER_ADDR}"
echo "Chain: $CHAIN"
echo "RPC: $RPC_URL"
echo "Initial authorized hubs: ${INITIAL_HUBS:-(deployer only)}"
echo ""

read -p "Continue? (y/N) " CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo "Aborted."
    PRIVATE_KEY="REDACTED"
    DEPLOYER_PRIVATE_KEY="REDACTED"
    exit 0
fi

# Default: deployer is the first authorized hub
INITIAL_HUBS="${INITIAL_HUBS:-$DEPLOYER_ADDR}"

echo ""
echo "Deploying AIMarketCapabilityNFT..."

export PRIVATE_KEY="0x${PRIVATE_KEY}"
export INITIAL_HUBS

forge script script/DeployNFT.s.sol \
    --rpc-url "$RPC_URL" \
    --broadcast \
    --private-key "0x${PRIVATE_KEY}" \
    $( [ -n "$ETHERSCAN_API_KEY" ] && echo "--verify --verifier-url $VERIFIER_URL --etherscan-api-key $ETHERSCAN_API_KEY" ) \
    ${FORGE_ARGS:-}

DEPLOY_EXIT=$?

PRIVATE_KEY="REDACTED"
DEPLOYER_PRIVATE_KEY="REDACTED"
unset PRIVATE_KEY
unset DEPLOYER_PRIVATE_KEY
unset INITIAL_HUBS

history -c 2>/dev/null || true
history -w 2>/dev/null || true

echo ""
if [ $DEPLOY_EXIT -eq 0 ]; then
    echo "=== Deploy complete ==="
    echo "Private key cleared from environment."
    echo ""
    echo "Next steps:"
    echo "  1. Copy the deployed address from the logs above"
    echo "  2. Add to your hub .env:"
    echo "       AIMARKET_NFT_CONTRACT=<deployed_address>"
    echo "       AIMARKET_NFT_CHAIN_RPC=$RPC_URL"
    echo "       AIMARKET_NFT_CHAIN=$CHAIN"
    echo "       AIMARKET_NFT_OWNER_KEY=<owner_private_key_kept_separately>"
    echo "  3. To authorize additional hubs later:"
    echo "       cast send <NFT_ADDR> 'setAuthorizedHub(address,bool)' <HUB> true \\"
    echo "         --private-key <OWNER_KEY> --rpc-url $RPC_URL"
else
    echo "=== Deploy FAILED (exit $DEPLOY_EXIT) ==="
    echo "Private key cleared from environment."
fi

exit $DEPLOY_EXIT
