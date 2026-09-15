#!/usr/bin/env bash
# =============================================================================
# transfer_contract_ownership.sh — Post-deploy: transfer contract ownership
# from deployer EOA to a Gnosis Safe multisig.
#
# This is step 1 of the two-step process. After this, the Safe signers must
# coordinate to call acceptOwnership() (see AcceptOwnership.s.sol or use the
# Safe Transaction Builder).
#
# Usage:
#   # Ledger flow (RECOMMENDED for mainnet — key never leaves device)
#   SAFE_ADDRESS=0xYourSafe... CONTRACT_ADDRESS=0xEscrow... \
#   RPC_URL=<rpc> \
#     ./scripts/transfer_contract_ownership.sh --ledger
#
#   # Custom Ledger derivation
#   SAFE_ADDRESS=0x... CONTRACT_ADDRESS=0x... RPC_URL=<rpc> \
#     ./scripts/transfer_contract_ownership.sh --ledger --derivation "m/44'/60'/1'/0/0"
#
#   # Private-key flow (only for testnet / CI — key is visible in `ps aux`
#   # for the duration of the cast send call)
#   SAFE_ADDRESS=0x... CONTRACT_ADDRESS=0x... \
#   PRIVATE_KEY=<deployer_key> RPC_URL=<rpc> \
#     ./scripts/transfer_contract_ownership.sh
#
#   # Check current ownership state (no signing key needed)
#   CONTRACT_ADDRESS=0x... RPC_URL=<rpc> \
#     ./scripts/transfer_contract_ownership.sh --check
#
# Environment:
#   SAFE_ADDRESS        — Gnosis Safe (or any multisig) address
#   CONTRACT_ADDRESS    — Deployed contract address
#   RPC_URL             — Chain RPC endpoint
#   PRIVATE_KEY         — Current owner's private key (omit if using --ledger)
#   LEDGER_DERIVATION   — Optional override for --ledger (default m/44'/60'/0'/0/0)
#   LEDGER_FROM         — Optional explicit Ledger sender address (skips cast wallet probe)
# =============================================================================
set -euo pipefail

# `${var,,}` is bash 4+. macOS ships bash 3.2, where it is not a graceful
# degradation but a hard `bad substitution` — and this script is normally run
# from the operator's laptop against mainnet, so the whole ownership handover
# died on the first address comparison. Compare through this instead.
lower() { printf '%s' "${1-}" | tr '[:upper:]' '[:lower:]'; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ── Parse args ──────────────────────────────────────────────────────────────
CHECK_ONLY=0
USE_LEDGER=0
# The single quotes of a hardened BIP-32 path cannot live inside `${x:-...}`:
# bash 3.2 (what macOS ships, and this runs from the operator's laptop) starts a
# quoted string on the first one and reports `unexpected EOF` for the whole file —
# the script would not parse at all, let alone reach a Ledger. Default separately.
_DEFAULT_LEDGER_DERIVATION="m/44'/60'/0'/0/0"
LEDGER_DERIVATION="${LEDGER_DERIVATION:-$_DEFAULT_LEDGER_DERIVATION}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --check)       CHECK_ONLY=1; shift ;;
        --ledger)      USE_LEDGER=1; shift ;;
        --derivation)  LEDGER_DERIVATION="$2"; shift 2 ;;
        *)             echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

# ── Validate inputs ─────────────────────────────────────────────────────────
die() { echo "ERROR: $*" >&2; exit 1; }

if [[ "$CHECK_ONLY" -eq 0 ]]; then
    SAFE_ADDRESS="${SAFE_ADDRESS:-}"
    [[ -n "$SAFE_ADDRESS" ]] || die "SAFE_ADDRESS is required (0x... Safe multisig address)"
    if [[ "$USE_LEDGER" -eq 1 ]]; then
        :  # No PRIVATE_KEY when --ledger
    else
        PRIVATE_KEY="${PRIVATE_KEY:-}"
        [[ -n "$PRIVATE_KEY" ]] || die "PRIVATE_KEY is required (current owner's key) — or pass --ledger"
    fi
fi

CONTRACT_ADDRESS="${CONTRACT_ADDRESS:-}"
RPC_URL="${RPC_URL:-http://localhost:8545}"

[[ -n "$CONTRACT_ADDRESS" ]] || die "CONTRACT_ADDRESS is required"

# ── Check cast is available ─────────────────────────────────────────────────
if ! command -v cast &>/dev/null; then
    die "cast not found. Install Foundry: curl -L https://foundry.paradigm.xyz | bash"
fi

export ETH_RPC_URL="$RPC_URL"

echo "═══ Contract Ownership Transfer ═══"
echo "  RPC:      $RPC_URL"
echo "  Contract: $CONTRACT_ADDRESS"
echo ""

# ── Read current state ──────────────────────────────────────────────────────
CURRENT_OWNER=$(cast call "$CONTRACT_ADDRESS" "owner()(address)" 2>/dev/null || echo "ERROR")
PENDING_OWNER=$(cast call "$CONTRACT_ADDRESS" "pendingOwner()(address)" 2>/dev/null || echo "0x0000000000000000000000000000000000000000")

echo "Current owner:   $CURRENT_OWNER"
echo "Pending owner:   $PENDING_OWNER"

if [[ "$CURRENT_OWNER" == "ERROR" ]]; then
    die "Cannot read owner() — is the contract deployed at this address?"
fi

# ── Check-only mode ─────────────────────────────────────────────────────────
if [[ "$CHECK_ONLY" -eq 1 ]]; then
    echo ""
    if [[ "$CURRENT_OWNER" == "$SAFE_ADDRESS" ]]; then
        echo "✅ Contract is owned by the Safe."
    elif [[ "$PENDING_OWNER" == "$SAFE_ADDRESS" ]]; then
        echo "🟡 Transfer to Safe is pending. Safe must call acceptOwnership()."
    else
        echo "❌ Contract is NOT owned by Safe (owner=$CURRENT_OWNER)."
        echo "   Run this script without --check to initiate transfer."
    fi
    exit 0
fi

# ── Resolve deployer address ────────────────────────────────────────────────
if [[ "$USE_LEDGER" -eq 1 ]]; then
    if [[ -n "${LEDGER_FROM:-}" ]]; then
        DEPLOYER_ADDR="$LEDGER_FROM"
    else
        DEPLOYER_ADDR=$(cast wallet address --ledger --mnemonic-derivation-path "$LEDGER_DERIVATION" 2>/dev/null || true)
        [[ -n "$DEPLOYER_ADDR" ]] || die "Cannot read Ledger address. Unlock device, open Ethereum app, or set LEDGER_FROM=0x..."
    fi
else
    DEPLOYER_ADDR=$(cast wallet address --private-key "$PRIVATE_KEY" 2>/dev/null)
fi

echo "Deployer:        $DEPLOYER_ADDR"
echo "Signing:         $( [[ "$USE_LEDGER" -eq 1 ]] && echo "Ledger ($LEDGER_DERIVATION)" || echo "private key" )"
echo ""

# ── Verify current owner matches our key ────────────────────────────────────
if [[ "$(lower "${CURRENT_OWNER}")" != "$(lower "${DEPLOYER_ADDR}")" ]]; then
    echo "WARNING: Current owner ($CURRENT_OWNER) does not match"
    echo "         the provided key address ($DEPLOYER_ADDR)."
    echo "         You are not the current owner. Transfer will likely fail."
    echo ""
    read -rp "Continue anyway? (y/N) " confirm
    [[ "$(lower "${confirm}")" == "y" ]] || exit 1
fi

# ── Check if already pending ────────────────────────────────────────────────
PENDING_ZERO="0x0000000000000000000000000000000000000000"
if [[ "$(lower "${PENDING_OWNER}")" != "$(lower "${PENDING_ZERO}")" ]]; then
    if [[ "$(lower "${PENDING_OWNER}")" == "$(lower "${SAFE_ADDRESS}")" ]]; then
        echo ""
        echo "✅ Ownership transfer already pending for $SAFE_ADDRESS."
        echo "   No on-chain action needed from deployer."
        echo "   Safe signers must now call acceptOwnership()."
        echo ""
        echo "   ⚠️  AcceptOwnership.s.sol works ONLY when the pending owner"
        echo "      is an EOA (forge script transmits from a single key)."
        echo "      For a real Gnosis Safe multisig, use the Safe Transaction Builder:"
        echo "       1. Build calldata: cast calldata \"acceptOwnership()\""
        echo "       2. Create Safe tx: to=$CONTRACT_ADDRESS, data=<calldata>, value=0"
        echo "       3. Collect N-of-M signatures, execute."
        exit 0
    else
        echo ""
        echo "⚠️  A different pending owner exists: $PENDING_OWNER"
        echo "   This will be overwritten. Continuing..."
    fi
fi

# ── Initiate transfer ───────────────────────────────────────────────────────
echo ""
echo "Initiating ownership transfer to Safe: $SAFE_ADDRESS"
echo ""

if [[ "$USE_LEDGER" -eq 1 ]]; then
    # N-3: Ledger path — key never touches RAM/argv, not visible in ps aux.
    TX_HASH=$(cast send "$CONTRACT_ADDRESS" \
        "transferOwnership(address)" "$SAFE_ADDRESS" \
        --ledger --mnemonic-derivation-path "$LEDGER_DERIVATION" \
        --from "$DEPLOYER_ADDR" \
        --json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('transactionHash','UNKNOWN'))" 2>/dev/null || echo "UNKNOWN")
else
    TX_HASH=$(cast send --private-key "$PRIVATE_KEY" "$CONTRACT_ADDRESS" \
        "transferOwnership(address)" "$SAFE_ADDRESS" \
        --json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('transactionHash','UNKNOWN'))" 2>/dev/null || echo "UNKNOWN")
fi

if [[ "$TX_HASH" == "UNKNOWN" ]]; then
    if [[ "$USE_LEDGER" -eq 1 ]]; then
        die "Transaction failed. Check Ledger connection, RPC_URL, and on-chain state."
    else
        die "Transaction failed. Check PRIVATE_KEY, RPC_URL, and on-chain state."
    fi
fi

echo "Transaction:     $TX_HASH"
echo ""

# ── Verify ──────────────────────────────────────────────────────────────────
sleep 3
NEW_PENDING=$(cast call "$CONTRACT_ADDRESS" "pendingOwner()(address)" 2>/dev/null || echo "ERROR")

if [[ "$(lower "${NEW_PENDING}")" == "$(lower "${SAFE_ADDRESS}")" ]]; then
    echo "✅ Ownership transfer initiated successfully."
    echo "   Pending owner: $SAFE_ADDRESS"
    echo ""
    echo "═══ Next step — Safe signers must accept ownership ═══"
    echo ""
    echo "For a Gnosis Safe multisig, use the Safe Transaction Builder:"
    echo "  1. calldata = \$(cast calldata \"acceptOwnership()\")"
    echo "  2. Create Safe transaction:"
    echo "       to:      $CONTRACT_ADDRESS"
    echo "       data:    \$calldata"
    echo "       value:   0"
    echo "  3. Collect N-of-M signatures"
    echo "  4. Execute"
    echo ""
    echo "If pending owner is an EOA (testnet drill only), you can use"
    echo "AcceptOwnership.s.sol (see contracts/evm/script/AcceptOwnership.s.sol)."
    echo ""
    echo "Verify manually:"
    echo "  cast call $CONTRACT_ADDRESS \"pendingOwner()(address)\""
    echo "  cast call $CONTRACT_ADDRESS \"owner()(address)\""
elif [[ "$NEW_PENDING" == "ERROR" ]]; then
    echo "❌ Failed to verify. Check the transaction on a block explorer."
    echo "   TX: $TX_HASH"
else
    echo "❌ Unexpected pending owner: $NEW_PENDING (expected $SAFE_ADDRESS)"
    echo "   Check TX: $TX_HASH"
fi
