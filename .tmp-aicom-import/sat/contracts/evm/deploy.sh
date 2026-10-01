#!/usr/bin/env bash
# Deploy AIMarketEscrow to an EVM chain.
#
# ⚠️  This deploys the ROOT AIMarketEscrow contract (aimarket-hub escrow).
#    For ACEX capital-markets contracts, use acex/contracts/evm/deploy.sh instead.
#    The two sets are INDEPENDENT — deploying the wrong one will give you a
#    contract that doesn't match your hub/ACEX configuration.
#
# Two signing modes:
#   1. --ledger      Hardware wallet (RECOMMENDED for mainnet)
#                    Key never leaves the device; nothing visible in ps aux.
#   2. private key   Pasted at console prompt, hidden input, cleared from
#                    env and history immediately after broadcast.
#
# Usage:
#   cd contracts/evm
#   ./deploy.sh base                                          # private key prompt
#   ./deploy.sh base --ledger                                 # hw wallet, default path
#   ./deploy.sh base --ledger --derivation "m/44'/60'/1'/0/0" # custom path
#   ./deploy.sh base-sepolia
#   ./deploy.sh ethereum
#   ./deploy.sh arbitrum
#
# Env overrides:
#   INITIAL_HUBS=0x..,0x..    initial authorized hub addresses
#   INITIAL_TOKENS=0x..,0x..  initial whitelisted USDT/USDC addresses
#   FORGE_ARGS="..."          extra args appended to forge script

set -euo pipefail

CHAIN="${1:-}"
if [ -z "$CHAIN" ]; then
    echo "Usage: $0 <chain> [--ledger [--derivation PATH] [--sender 0x...]]"
    echo "  chain: base | base-sepolia | ethereum | arbitrum"
    exit 1
fi
shift || true

# ── Parse signing options ────────────────────────────────────────
USE_LEDGER=0
LEDGER_DERIVATION="m/44'/60'/0'/0/0"
LEDGER_SENDER=""

while [ $# -gt 0 ]; do
    case "$1" in
        --ledger)        USE_LEDGER=1; shift ;;
        --derivation)    LEDGER_DERIVATION="$2"; shift 2 ;;
        --sender)        LEDGER_SENDER="$2"; shift 2 ;;
        *)               echo "Unknown option: $1"; exit 1 ;;
    esac
done

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

# ── Banner ───────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  AIMarketEscrow — Deploy to ${CHAIN}"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

if [ "$USE_LEDGER" -eq 1 ]; then
    # ── Ledger path: key stays on device ─────────────────────────
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
    # ── Private-key path: paste at hidden prompt ─────────────────
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
    DEPLOYER_ADDR="$(cast wallet address "0x${PRIVATE_KEY}" 2>/dev/null || echo unknown)"
fi

echo ""
echo "Deployer address: $DEPLOYER_ADDR"
echo "Chain: $CHAIN"
echo "RPC: $RPC_URL"
echo "Signing: $( [ "$USE_LEDGER" -eq 1 ] && echo "Ledger ($LEDGER_DERIVATION)" || echo "console private key" )"
echo ""

read -p "Continue? (y/N) " CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo "Aborted."
    [ -n "${PRIVATE_KEY:-}" ] && PRIVATE_KEY="REDACTED" && unset PRIVATE_KEY
    [ -n "${DEPLOYER_PRIVATE_KEY:-}" ] && DEPLOYER_PRIVATE_KEY="REDACTED" && unset DEPLOYER_PRIVATE_KEY
    exit 0
fi

echo ""
echo "Deploying..."

# Default: deployer is the first authorized hub
INITIAL_HUBS="${INITIAL_HUBS:-$DEPLOYER_ADDR}"
export INITIAL_HUBS
export INITIAL_TOKENS="${INITIAL_TOKENS:-}"

# ── Run Foundry deploy ───────────────────────────────────────────
VERIFY_FLAGS=""
if [ -n "$ETHERSCAN_API_KEY" ]; then
    VERIFY_FLAGS="--verify --verifier-url $VERIFIER_URL --etherscan-api-key $ETHERSCAN_API_KEY"
fi

if [ "$USE_LEDGER" -eq 1 ]; then
    # Foundry script forge has --ledger flag — the Forge `vm.envUint("PRIVATE_KEY")`
    # in Deploy.s.sol means we must not use that script when signing via Ledger.
    # Instead deploy via `forge create` with Ledger, then run the constructor
    # logic by inlining bytecode.
    echo ""
    echo "⚠️  NOTE: The current Deploy.s.sol uses vm.envUint('PRIVATE_KEY') and"
    echo "    cannot drive a Ledger directly. To deploy with Ledger:"
    echo ""
    echo "    forge create AIMarketEscrow.sol:AIMarketEscrow \\"
    echo "        --rpc-url $RPC_URL \\"
    echo "        --ledger --mnemonic-derivation-path \"$LEDGER_DERIVATION\" \\"
    echo "        --sender $DEPLOYER_ADDR \\"
    echo "        --constructor-args \"[$INITIAL_HUBS]\" \"[$INITIAL_TOKENS]\" \\"
    echo "        $VERIFY_FLAGS"
    echo ""
    echo "    Then call setHubAuthorization / setTokenWhitelist for any extras."
    echo ""
    read -p "Run the forge create command above now? (y/N) " RUN_FORGE
    if [ "$RUN_FORGE" != "y" ] && [ "$RUN_FORGE" != "Y" ]; then
        echo "Aborted — copy the command above to run manually."
        exit 0
    fi
    # shellcheck disable=SC2086
    forge create AIMarketEscrow.sol:AIMarketEscrow \
        --rpc-url "$RPC_URL" \
        --ledger --mnemonic-derivation-path "$LEDGER_DERIVATION" \
        --sender "$DEPLOYER_ADDR" \
        --constructor-args "[$INITIAL_HUBS]" "[$INITIAL_TOKENS]" \
        $VERIFY_FLAGS \
        ${FORGE_ARGS:-}
    DEPLOY_EXIT=$?
else
    # Key stays in the environment only (Deploy.s.sol reads vm.envUint("PRIVATE_KEY")).
    # Never pass --private-key on the CLI — it shows up in `ps` /proc cmdline.
    export PRIVATE_KEY="0x${PRIVATE_KEY}"
    # shellcheck disable=SC2086
    forge script script/Deploy.s.sol \
        --rpc-url "$RPC_URL" \
        --broadcast \
        $VERIFY_FLAGS \
        ${FORGE_ARGS:-}
    DEPLOY_EXIT=$?
fi

# ── IMMEDIATELY clear key from env and shell ─────────────────────
if [ "$USE_LEDGER" -ne 1 ]; then
    PRIVATE_KEY="REDACTED"
    DEPLOYER_PRIVATE_KEY="REDACTED"
    unset PRIVATE_KEY
    unset DEPLOYER_PRIVATE_KEY
fi
unset INITIAL_HUBS
unset INITIAL_TOKENS
# Note: `history -c` would only affect THIS subshell's history (already
# gone on exit). Cleaning the parent shell's history is the operator's job:
#   history -d <line>  (or shred -u ~/.bash_history if paranoid)

echo ""
if [ $DEPLOY_EXIT -eq 0 ]; then
    echo "=== Deploy complete ==="
    echo "Set AIMARKET_ESCROW_EVM_ADDRESS= in your .env"
else
    echo "=== Deploy FAILED (exit $DEPLOY_EXIT) ==="
fi

exit $DEPLOY_EXIT
