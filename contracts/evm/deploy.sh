#!/usr/bin/env bash
# Deploy AIMarketEscrow to an EVM chain.
# Private key is read from console (no echo) and NEVER persisted.
#
# Usage:
#   cd contracts/evm
#   ./deploy.sh base          # Base mainnet
#   ./deploy.sh base-sepolia  # Base Sepolia testnet
#   ./deploy.sh ethereum      # Ethereum mainnet
#   ./deploy.sh arbitrum      # Arbitrum One
#
# What happens:
#   - You paste the private key at the prompt (input hidden)
#   - Foundry deploys the contract
#   - Key is cleared from shell history and env immediately after
#   - NOTHING is written to disk

set -euo pipefail

CHAIN="${1:-}"
if [ -z "$CHAIN" ]; then
    echo "Usage: $0 <chain>"
    echo "  base | base-sepolia | ethereum | arbitrum"
    exit 1
fi

# ── RPC mapping ──────────────────────────────────────────────────
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
        echo "Supported: base | base-sepolia | ethereum | arbitrum"
        exit 1
        ;;
esac

# ── Read private key from console ────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  AIMarketEscrow — Deploy to ${CHAIN}"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Paste the deployer private key (input hidden):             ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Read with hidden input (no echo to terminal, not even stars)
if [ -t 0 ]; then
    # Terminal available — use read -s
    read -s -p "Private key (0x...): " DEPLOYER_PRIVATE_KEY
    echo ""  # newline after hidden input
else
    # Non-interactive — read from stdin (pipe)
    read -r DEPLOYER_PRIVATE_KEY
fi

# Validate format
if [ -z "$DEPLOYER_PRIVATE_KEY" ]; then
    echo "ERROR: No private key provided."
    exit 1
fi

if [[ ! "$DEPLOYER_PRIVATE_KEY" =~ ^(0x)?[0-9a-fA-F]{64}$ ]]; then
    echo "ERROR: Private key must be 64 hex characters (with optional 0x prefix)."
    # Key is invalid, but still clear it
    DEPLOYER_PRIVATE_KEY="REDACTED"
    exit 1
fi

# Normalize: strip 0x prefix if present (Foundry handles both, but safer)
PRIVATE_KEY="${DEPLOYER_PRIVATE_KEY#0x}"

echo ""
echo "Deployer address: $(cast wallet address "0x${PRIVATE_KEY}" 2>/dev/null || echo "unknown")"
echo "Chain: $CHAIN"
echo "RPC: $RPC_URL"
echo ""

read -p "Continue? (y/N) " CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo "Aborted."
    PRIVATE_KEY="REDACTED"
    DEPLOYER_PRIVATE_KEY="REDACTED"
    exit 0
fi

echo ""
echo "Deploying..."

# ── Build initial hub/token args ─────────────────────────────────
# Default: deployer is the first authorized hub
DEPLOYER_ADDR=$(cast wallet address "0x${PRIVATE_KEY}")
INITIAL_HUBS="${INITIAL_HUBS:-$DEPLOYER_ADDR}"

# ── Run Foundry deploy ───────────────────────────────────────────
export PRIVATE_KEY="0x${PRIVATE_KEY}"
export INITIAL_HUBS
export INITIAL_TOKENS="${INITIAL_TOKENS:-}"

forge script script/Deploy.s.sol \
    --rpc-url "$RPC_URL" \
    --broadcast \
    --private-key "0x${PRIVATE_KEY}" \
    $( [ -n "$ETHERSCAN_API_KEY" ] && echo "--verify --verifier-url $VERIFIER_URL --etherscan-api-key $ETHERSCAN_API_KEY" ) \
    ${FORGE_ARGS:-}

DEPLOY_EXIT=$?

# ── IMMEDIATELY clear key from env and shell ─────────────────────
PRIVATE_KEY="REDACTED"
DEPLOYER_PRIVATE_KEY="REDACTED"
unset PRIVATE_KEY
unset DEPLOYER_PRIVATE_KEY
unset INITIAL_HUBS
unset INITIAL_TOKENS

# Also clear from bash history (if we're in an interactive session)
history -c 2>/dev/null || true
history -w 2>/dev/null || true

echo ""
if [ $DEPLOY_EXIT -eq 0 ]; then
    echo "=== Deploy complete ==="
    echo "Private key cleared from environment."
    echo "Set AIMARKET_ESCROW_EVM_ADDRESS= in your .env"
else
    echo "=== Deploy FAILED (exit $DEPLOY_EXIT) ==="
    echo "Private key cleared from environment."
fi

exit $DEPLOY_EXIT
