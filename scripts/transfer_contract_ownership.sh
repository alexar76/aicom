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
#   # For escrow contract
#   SAFE_ADDRESS=0xYourSafe... CONTRACT_ADDRESS=0xEscrow... \
#   PRIVATE_KEY=<deployer_key> RPC_URL=<rpc> \
#     ./scripts/transfer_contract_ownership.sh
#
#   # For NFT contract
#   SAFE_ADDRESS=0xYourSafe... CONTRACT_ADDRESS=0xNFT... \
#   PRIVATE_KEY=<deployer_key> RPC_URL=<rpc> \
#     ./scripts/transfer_contract_ownership.sh
#
#   # Check current ownership state
#   CONTRACT_ADDRESS=0x... RPC_URL=<rpc> \
#     ./scripts/transfer_contract_ownership.sh --check
#
# Environment:
#   SAFE_ADDRESS        — Gnosis Safe (or any multisig) address
#   CONTRACT_ADDRESS    — Deployed contract address
#   PRIVATE_KEY         — Current owner's private key (deployer)
#   RPC_URL             — Chain RPC endpoint
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ── Parse args ──────────────────────────────────────────────────────────────
CHECK_ONLY=0
if [[ "${1:-}" == "--check" ]]; then
    CHECK_ONLY=1
fi

# ── Validate inputs ─────────────────────────────────────────────────────────
die() { echo "ERROR: $*" >&2; exit 1; }

if [[ "$CHECK_ONLY" -eq 0 ]]; then
    SAFE_ADDRESS="${SAFE_ADDRESS:-}"
    PRIVATE_KEY="${PRIVATE_KEY:-}"
    [[ -n "$SAFE_ADDRESS" ]]  || die "SAFE_ADDRESS is required (0x... Safe multisig address)"
    [[ -n "$PRIVATE_KEY" ]]   || die "PRIVATE_KEY is required (current owner's key)"
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

# ── Verify current owner matches our key ────────────────────────────────────
DEPLOYER_ADDR=$(cast wallet address --private-key "$PRIVATE_KEY" 2>/dev/null)
echo "Deployer:        $DEPLOYER_ADDR"

if [[ "${CURRENT_OWNER,,}" != "${DEPLOYER_ADDR,,}" ]]; then
    echo ""
    echo "WARNING: Current owner ($CURRENT_OWNER) does not match"
    echo "         the provided PRIVATE_KEY address ($DEPLOYER_ADDR)."
    echo "         You are not the current owner. Transfer will likely fail."
    echo ""
    read -rp "Continue anyway? (y/N) " confirm
    [[ "${confirm,,}" == "y" ]] || exit 1
fi

# ── Check if already pending ────────────────────────────────────────────────
PENDING_ZERO="0x0000000000000000000000000000000000000000"
if [[ "${PENDING_OWNER,,}" != "${PENDING_ZERO,,}" ]]; then
    if [[ "${PENDING_OWNER,,}" == "${SAFE_ADDRESS,,}" ]]; then
        echo ""
        echo "✅ Ownership transfer already pending for $SAFE_ADDRESS."
        echo "   No on-chain action needed from deployer."
        echo "   Safe signers must now call acceptOwnership()."
        echo ""
        echo "   Via AcceptOwnership.s.sol:"
        echo "     SAFE_ADDRESS=$SAFE_ADDRESS CONTRACT_ADDRESS=$CONTRACT_ADDRESS \\"
        echo "       PRIVATE_KEY=<safe_signer_key> RPC_URL=$RPC_URL \\"
        echo "       forge script contracts/evm/script/AcceptOwnership.s.sol \\"
        echo "         --rpc-url $RPC_URL --broadcast"
        echo ""
        echo "   Via Safe Transaction Builder:"
        echo "     1. Build calldata: cast calldata \"acceptOwnership()\""
        echo "     2. Create Safe tx: to=$CONTRACT_ADDRESS, data=<calldata>, value=0"
        echo "     3. Collect N-of-M signatures, execute."
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

TX_HASH=$(cast send --private-key "$PRIVATE_KEY" "$CONTRACT_ADDRESS" \
    "transferOwnership(address)" "$SAFE_ADDRESS" \
    --json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('transactionHash','UNKNOWN'))" 2>/dev/null || echo "UNKNOWN")

if [[ "$TX_HASH" == "UNKNOWN" ]]; then
    die "Transaction failed. Check PRIVATE_KEY, RPC_URL, and on-chain state."
fi

echo "Transaction:     $TX_HASH"
echo ""

# ── Verify ──────────────────────────────────────────────────────────────────
sleep 3
NEW_PENDING=$(cast call "$CONTRACT_ADDRESS" "pendingOwner()(address)" 2>/dev/null || echo "ERROR")

if [[ "${NEW_PENDING,,}" == "${SAFE_ADDRESS,,}" ]]; then
    echo "✅ Ownership transfer initiated successfully."
    echo "   Pending owner: $SAFE_ADDRESS"
    echo ""
    echo "═══ Next step — Safe signers must accept ownership ═══"
    echo ""
    echo "Option A — Use AcceptOwnership.s.sol (forge-native):"
    echo "  SAFE_ADDRESS=$SAFE_ADDRESS \\"
    echo "  CONTRACT_ADDRESS=$CONTRACT_ADDRESS \\"
    echo "  PRIVATE_KEY=<one_safe_signer_key> \\"
    echo "    forge script contracts/evm/script/AcceptOwnership.s.sol \\"
    echo "      --rpc-url $RPC_URL --broadcast"
    echo ""
    echo "Option B — Use Safe Transaction Builder (recommended):"
    echo "  1. calldata = \$(cast calldata \"acceptOwnership()\")"
    echo "  2. Create Safe transaction:"
    echo "       to:      $CONTRACT_ADDRESS"
    echo "       data:    \$calldata"
    echo "       value:   0"
    echo "  3. Collect N-of-M signatures"
    echo "  4. Execute"
    echo ""
    echo "Option C — Verify manually:"
    echo "  cast call $CONTRACT_ADDRESS \"pendingOwner()(address)\""
    echo "  cast call $CONTRACT_ADDRESS \"owner()(address)\""
elif [[ "$NEW_PENDING" == "ERROR" ]]; then
    echo "❌ Failed to verify. Check the transaction on a block explorer."
    echo "   TX: $TX_HASH"
else
    echo "❌ Unexpected pending owner: $NEW_PENDING (expected $SAFE_ADDRESS)"
    echo "   Check TX: $TX_HASH"
fi
