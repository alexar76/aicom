#!/usr/bin/env bash
# =============================================================================
# setup.sh — One-time Groth16 trusted setup for input_validity circuit.
#
# WHAT THIS DOES (in order):
#   1. Compile input_validity.circom    → R1CS + symbol files + WASM witness
#   2. Download or reuse a Powers-of-Tau (.ptau) file for BN254
#   3. Phase-2 ceremony (circuit-specific):
#        a. zkey generation
#        b. contributor entropy (you, deployer, anyone you trust)
#        c. verification-key export
#   4. Generate Solidity verifier contract
#
# RUN ONCE per circuit version. Outputs commit to git (verifier.sol,
# verification_key.json) but NOT the proving key zkey (operator artifact;
# only the prover needs it).
#
# Requirements:
#   - circom 2.1.6+
#   - snarkjs CLI (npm i -g snarkjs)
#   - circomlib (npm i circomlib in this dir, or set CIRCOMLIB_PATH)
#
# Output layout:
#   contracts/zk/build/
#     input_validity.r1cs
#     input_validity.sym
#     input_validity_js/input_validity.wasm
#     input_validity_0001.zkey            ← prover (keep private to operator)
#     verification_key.json               ← public, committed
#   contracts/zk/verifier/Verifier.sol    ← public, committed
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CIRCUIT="circuits/input_validity.circom"
BUILD="build"
CIRCUIT_NAME="input_validity"

PTAU_POWER="${PTAU_POWER:-14}"    # 2^14 = 16384 constraints — plenty for our circuit
PTAU_FILE="pot${PTAU_POWER}_final.ptau"
PTAU_URL="https://hermez.s3-eu-west-1.amazonaws.com/${PTAU_FILE}"

echo "═══════════════════════════════════════════════════════════════"
echo "  ZK Trusted Setup — input_validity circuit"
echo "═══════════════════════════════════════════════════════════════"
echo "  Output:    $BUILD/"
echo "  Verifier:  verifier/Verifier.sol"
echo "  ptau:      $PTAU_FILE (power $PTAU_POWER)"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ── 0. Tool checks ───────────────────────────────────────────────
command -v circom >/dev/null  || { echo "ERROR: install circom 2.1.6+"; exit 1; }
command -v snarkjs >/dev/null || { echo "ERROR: install snarkjs (npm i -g snarkjs)"; exit 1; }

mkdir -p "$BUILD" "verifier"
cd "$BUILD"

# ── 1. Get ptau file ─────────────────────────────────────────────
if [ ! -f "$PTAU_FILE" ]; then
    echo "Downloading Powers-of-Tau ($PTAU_FILE) — public Hermez ceremony output …"
    curl -L --fail "$PTAU_URL" -o "$PTAU_FILE"
    echo "Verifying ptau integrity …"
    snarkjs powersoftau verify "$PTAU_FILE"
else
    echo "Reusing existing $PTAU_FILE"
fi

# ── 2. Compile circuit ───────────────────────────────────────────
echo ""
echo "→ Compiling $CIRCUIT …"
CIRCOMLIB="${CIRCOMLIB_PATH:-../node_modules}"
if [ ! -d "$CIRCOMLIB/circomlib" ]; then
    echo "ERROR: circomlib not found at $CIRCOMLIB/circomlib"
    echo "       Run: npm i circomlib (in contracts/zk/)"
    exit 1
fi

circom "$ROOT/$CIRCUIT" --r1cs --wasm --sym -l "$CIRCOMLIB"

# ── 3. Generate zkey (phase 2 setup) ─────────────────────────────
echo ""
echo "→ Phase 2 setup — initial zkey …"
snarkjs groth16 setup "${CIRCUIT_NAME}.r1cs" "$PTAU_FILE" "${CIRCUIT_NAME}_0000.zkey"

echo ""
echo "→ Contributing entropy (you are contributor #1) …"
echo "   This adds randomness to the proving key — the security of the"
echo "   final zkey requires that AT LEAST ONE contributor's entropy"
echo "   is honestly destroyed after the ceremony."
echo ""
read -p "Press Enter to continue, or paste extra entropy text (will be combined with /dev/urandom): " EXTRA_ENTROPY

ENTROPY_BLOB="$(head -c 256 /dev/urandom | xxd -p)${EXTRA_ENTROPY:-}"
echo "$ENTROPY_BLOB" | snarkjs groth16 contribute "${CIRCUIT_NAME}_0000.zkey" "${CIRCUIT_NAME}_0001.zkey" \
    --name="operator-$(date +%Y%m%d-%H%M%S)" -v
unset ENTROPY_BLOB EXTRA_ENTROPY

# Optional: more contributors can be invited here (each runs the same
# contribute command, signing off with a tweet/commit). For a solo operator,
# one contribution is the minimum — but provides minimum security too.

# ── 4. Verify final zkey ─────────────────────────────────────────
echo ""
echo "→ Verifying final zkey integrity …"
snarkjs zkey verify "${CIRCUIT_NAME}.r1cs" "$PTAU_FILE" "${CIRCUIT_NAME}_0001.zkey"

# ── 5. Export verification key ───────────────────────────────────
echo ""
echo "→ Exporting public verification key …"
snarkjs zkey export verificationkey "${CIRCUIT_NAME}_0001.zkey" verification_key.json
cp verification_key.json "$ROOT/verifier/verification_key.json"

# ── 6. Generate Solidity verifier ────────────────────────────────
echo ""
echo "→ Generating Solidity verifier contract …"
snarkjs zkey export solidityverifier "${CIRCUIT_NAME}_0001.zkey" "$ROOT/verifier/Verifier.sol"

# Replace generic 'Groth16Verifier' name with our specific one
sed -i.bak 's/Groth16Verifier/AIMarketInputValidityVerifier/g' "$ROOT/verifier/Verifier.sol"
rm "$ROOT/verifier/Verifier.sol.bak" 2>/dev/null || true

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ✅ Setup complete"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "  Public (commit these):"
echo "    verifier/Verifier.sol               → deploy to chain"
echo "    verifier/verification_key.json      → client-side verify"
echo ""
echo "  Operator-private (DO NOT COMMIT):"
echo "    build/${CIRCUIT_NAME}_0001.zkey     → prover artifact"
echo "    build/${CIRCUIT_NAME}_js/*          → witness generator"
echo ""
echo "  Next:"
echo "    1. forge create verifier/Verifier.sol:AIMarketInputValidityVerifier ..."
echo "    2. Set AIMARKET_ZK_VERIFIER_CONTRACT=0x… in hub .env"
echo "    3. Drop AIMARKET_ZK_SIMULATED=1 — real Groth16 takes over"
