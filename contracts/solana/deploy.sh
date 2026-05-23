#!/usr/bin/env bash
# Deploy aimarket-escrow to Solana.
# Private key is read from console (no echo) and NEVER persisted.
#
# Usage:
#   cd contracts/solana
#   ./deploy.sh devnet
#   ./deploy.sh mainnet
#
# The keypair is reconstructed from the private key bytes in-memory.
# Nothing is written to ~/.config/solana/id.json or any file.

set -euo pipefail

NETWORK="${1:-}"
if [ -z "$NETWORK" ]; then
    echo "Usage: $0 <network>"
    echo "  devnet | mainnet"
    exit 1
fi

case "$NETWORK" in
    devnet)
        RPC_URL="${SOLANA_RPC_DEVNET:-https://api.devnet.solana.com}"
        ;;
    mainnet)
        RPC_URL="${SOLANA_RPC_MAINNET:-https://api.mainnet-beta.solana.com}"
        ;;
    *)
        echo "Unknown network: $NETWORK"
        exit 1
        ;;
esac

# ── Read private key from console ────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  AIMarketEscrow (Solana) — Deploy to ${NETWORK}"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Paste the deployer private key (base58 JSON bytes):        ║"
echo "║  (input hidden — never saved to disk)                      ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

if [ -t 0 ]; then
    read -s -p "Private key (JSON bytes as base58 or [1,2,3,...]): " RAW_KEY
    echo ""
else
    read -r RAW_KEY
fi

if [ -z "$RAW_KEY" ]; then
    echo "ERROR: No private key provided."
    exit 1
fi

# ── Build temporary keypair (in-memory only) ─────────────────────
TMP_KEYFILE=$(mktemp)
chmod 600 "$TMP_KEYFILE"

# Handle both JSON array format [1,2,3,...] and base58 string
if [[ "$RAW_KEY" == \[* ]]; then
    echo "$RAW_KEY" > "$TMP_KEYFILE"
else
    # Assume base58 — convert to JSON bytes array
    python3 -c "
import json, sys, base58
key_bytes = base58.b58decode('$RAW_KEY')
print(json.dumps(list(key_bytes)))
" > "$TMP_KEYFILE"
fi

# Clear console variable
RAW_KEY="REDACTED"

# Show pubkey
PUBKEY=$(solana-keygen pubkey "$TMP_KEYFILE" 2>/dev/null || echo "unknown")
echo "Deployer pubkey: $PUBKEY"
echo "Network: $NETWORK"
echo "RPC: $RPC_URL"
echo ""

read -p "Continue? (y/N) " CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    rm -f "$TMP_KEYFILE"
    echo "Aborted."
    exit 0
fi

echo ""
echo "Building program..."

# ── Build ────────────────────────────────────────────────────────
anchor build 2>&1 || {
    echo "Build failed"
    rm -f "$TMP_KEYFILE"
    exit 1
}

# ── Deploy ───────────────────────────────────────────────────────
echo "Deploying to $NETWORK..."

solana program deploy \
    --url "$RPC_URL" \
    --keypair "$TMP_KEYFILE" \
    target/deploy/aimarket_escrow.so \
    ${DEPLOY_ARGS:-}

DEPLOY_EXIT=$?

# ── IMMEDIATELY remove keypair ───────────────────────────────────
rm -f "$TMP_KEYFILE"
unset RAW_KEY

echo ""
if [ $DEPLOY_EXIT -eq 0 ]; then
    echo "=== Deploy complete ==="
    echo "Program ID: A1M4rk3tEscrowChanne1Paym3nt5oLProg"
    echo "Temporary keypair DELETED."
else
    echo "=== Deploy FAILED (exit $DEPLOY_EXIT) ==="
    echo "Temporary keypair DELETED."
fi

exit $DEPLOY_EXIT
