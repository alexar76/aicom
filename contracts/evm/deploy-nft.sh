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
    echo "Usage: $0 <chain> [--ledger [--derivation PATH]]"
    echo "  chain: base | base-sepolia | ethereum | arbitrum"
    exit 1
fi
shift || true

USE_LEDGER=0
LEDGER_DERIVATION="m/44'/60'/0'/0/0"
LEDGER_SENDER=""
while [ $# -gt 0 ]; do
    case "$1" in
        --ledger)     USE_LEDGER=1; shift ;;
        --derivation) LEDGER_DERIVATION="$2"; shift 2 ;;
        --sender)     LEDGER_SENDER="$2"; shift 2 ;;
        *)            echo "Unknown option: $1"; exit 1 ;;
    esac
done

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
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

if [ "$USE_LEDGER" -eq 1 ]; then
    if [ -z "$LEDGER_SENDER" ]; then
        echo "Reading deployer address from Ledger (derivation: $LEDGER_DERIVATION) …"
        LEDGER_SENDER="$(cast wallet address --ledger --mnemonic-derivation-path "$LEDGER_DERIVATION" 2>/dev/null || true)"
        if [ -z "$LEDGER_SENDER" ]; then
            echo "ERROR: Could not read Ledger address. Unlock device and open the Ethereum app."
            exit 1
        fi
    fi
    DEPLOYER_ADDR="$LEDGER_SENDER"
else
    echo "Paste the deployer private key (input hidden) — or rerun with --ledger:"
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
fi

echo ""
echo "Deployer address: ${DEPLOYER_ADDR}"
echo "Chain: $CHAIN"
echo "RPC: $RPC_URL"
echo "Signing: $( [ "$USE_LEDGER" -eq 1 ] && echo "Ledger ($LEDGER_DERIVATION)" || echo "console private key" )"
echo "Initial authorized hubs: ${INITIAL_HUBS:-(deployer only)}"
echo ""

read -p "Continue? (y/N) " CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo "Aborted."
    [ -n "${PRIVATE_KEY:-}" ] && PRIVATE_KEY="REDACTED" && unset PRIVATE_KEY
    [ -n "${DEPLOYER_PRIVATE_KEY:-}" ] && DEPLOYER_PRIVATE_KEY="REDACTED" && unset DEPLOYER_PRIVATE_KEY
    exit 0
fi

INITIAL_HUBS="${INITIAL_HUBS:-$DEPLOYER_ADDR}"

echo ""
echo "Deploying AIMarketCapabilityNFT..."

VERIFY_FLAGS=""
if [ -n "$ETHERSCAN_API_KEY" ]; then
    VERIFY_FLAGS="--verify --verifier-url $VERIFIER_URL --etherscan-api-key $ETHERSCAN_API_KEY"
fi

if [ "$USE_LEDGER" -eq 1 ]; then
    # AIMarketCapabilityNFT constructor takes no args — initial hubs are set
    # via setAuthorizedHub() after deploy (one tx per hub on Ledger; OK for a
    # small initial set, scriptable for larger via cast send loops).
    # shellcheck disable=SC2086
    forge create AIMarketCapabilityNFT.sol:AIMarketCapabilityNFT \
        --rpc-url "$RPC_URL" \
        --ledger --mnemonic-derivation-path "$LEDGER_DERIVATION" \
        --sender "$DEPLOYER_ADDR" \
        $VERIFY_FLAGS \
        ${FORGE_ARGS:-}
    DEPLOY_EXIT=$?
    NFT_ADDR_HINT=" (copy 'Deployed to:' address from output above)"
else
    export PRIVATE_KEY="0x${PRIVATE_KEY}"
    export INITIAL_HUBS
    # shellcheck disable=SC2086
    forge script script/DeployNFT.s.sol \
        --rpc-url "$RPC_URL" \
        --broadcast \
        --private-key "0x${PRIVATE_KEY}" \
        $VERIFY_FLAGS \
        ${FORGE_ARGS:-}
    DEPLOY_EXIT=$?
    NFT_ADDR_HINT=""
fi

if [ "$USE_LEDGER" -ne 1 ]; then
    PRIVATE_KEY="REDACTED"
    DEPLOYER_PRIVATE_KEY="REDACTED"
    unset PRIVATE_KEY
    unset DEPLOYER_PRIVATE_KEY
fi
unset INITIAL_HUBS
# `history -c` in a subshell is a no-op for the parent's history; if you
# pasted a key into the calling shell, clear it yourself (`history -d N`).

echo ""
if [ $DEPLOY_EXIT -eq 0 ]; then
    echo "=== Deploy complete ==="
    echo ""
    echo "Next steps:${NFT_ADDR_HINT}"
    echo "  1. Copy the deployed address from the logs above"
    echo "  2. Add to your hub .env:"
    echo "       AIMARKET_NFT_CONTRACT=<deployed_address>"
    echo "       AIMARKET_NFT_CHAIN_RPC=$RPC_URL"
    echo "       AIMARKET_NFT_CHAIN=$CHAIN"
    echo "       AIMARKET_NFT_OWNER_KEY=<owner_private_key_kept_separately>"
    echo "  3. To authorize additional hubs later:"
    if [ "$USE_LEDGER" -eq 1 ]; then
        echo "       cast send <NFT_ADDR> 'setAuthorizedHub(address,bool)' <HUB> true \\"
        echo "         --ledger --mnemonic-derivation-path \"$LEDGER_DERIVATION\" \\"
        echo "         --from $DEPLOYER_ADDR --rpc-url $RPC_URL"
    else
        echo "       cast send <NFT_ADDR> 'setAuthorizedHub(address,bool)' <HUB> true \\"
        echo "         --ledger --mnemonic-derivation-path \"$LEDGER_DERIVATION\" \\"
        echo "         --rpc-url $RPC_URL"
        echo "     (or repeat this deploy script's private-key flow — but Ledger is preferred)"
    fi
else
    echo "=== Deploy FAILED (exit $DEPLOY_EXIT) ==="
    echo "Private key cleared from environment."
fi

exit $DEPLOY_EXIT
