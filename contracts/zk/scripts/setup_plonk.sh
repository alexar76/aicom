#!/usr/bin/env bash
# setup_plonk.sh — PLONK setup for the input_validity circuit.
#
# Unlike Groth16 (setup.sh), PLONK uses a *universal* structured reference
# string: a single public Powers-of-Tau (phase 1) is enough — there is NO
# per-circuit, multi-party trusted-setup ceremony, and no toxic waste to
# destroy. This is what lets us ship real ZK without running our own
# ceremony (closes KI-1).
#
# Outputs (committable, public):
#   verifier/verification_key.json   — public verifying key
#   verifier/Verifier.sol            — on-chain PlonkVerifier
# Build-only (regenerable, gitignored under build/):
#   build/input_validity.r1cs, build/input_validity_js/input_validity.wasm
#   build/input_validity_plonk.zkey  — proving key (NOT secret for PLONK;
#                                       deterministic from the public ptau)
#
# Prereqs: node, snarkjs (npm i), circom 2.x, circomlib (npm i).
# Usage:   bash contracts/zk/scripts/setup_plonk.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CIRCUIT="circuits/input_validity.circom"
NAME="input_validity"
BUILD="build"
OUT="verifier"
mkdir -p "$BUILD" "$OUT"

# Powers-of-Tau (phase 1) — public, universal. pot14 = 2^14 = 16384 cells,
# ample for this circuit (~1.7k PLONK constraints). The classic Hermez S3
# path 404s now; use the maintained mirror, fall back to S3 by canonical name.
PTAU="$BUILD/pot14_final.ptau"
PTAU_PRIMARY="https://storage.googleapis.com/zkevm/ptau/powersOfTau28_hez_final_14.ptau"
PTAU_FALLBACK="https://hermez.s3-eu-west-1.amazonaws.com/powersOfTau28_hez_final_14.ptau"

SNARKJS="${AIMARKET_ZK_SNARKJS:-npx --no-install snarkjs}"
CIRCOM="${CIRCOM_BIN:-circom}"

echo "== PLONK setup (universal — no ceremony) =="

# ── 1. Get ptau ───────────────────────────────────────────────────
if [ ! -f "$PTAU" ]; then
  echo "→ Downloading public Powers-of-Tau (pot14) …"
  curl -L --fail -o "$PTAU" "$PTAU_PRIMARY" \
    || curl -L --fail -o "$PTAU" "$PTAU_FALLBACK"
  echo "→ Verifying ptau integrity …"
  $SNARKJS powersoftau verify "$PTAU"
else
  echo "→ Reusing $PTAU"
fi

# ── 2. Compile circuit → r1cs + wasm ──────────────────────────────
echo "→ Compiling $CIRCUIT …"
"$CIRCOM" "$CIRCUIT" --r1cs --wasm -l node_modules -o "$BUILD"

# ── 3. PLONK setup (universal — no phase-2 ceremony) ──────────────
echo "→ PLONK setup → zkey …"
$SNARKJS plonk setup "$BUILD/${NAME}.r1cs" "$PTAU" "$BUILD/${NAME}_plonk.zkey"

# ── 4. Export public artifacts ────────────────────────────────────
echo "→ Exporting verification key + Solidity verifier …"
$SNARKJS zkey export verificationkey "$BUILD/${NAME}_plonk.zkey" "$OUT/verification_key.json"
$SNARKJS zkey export solidityverifier "$BUILD/${NAME}_plonk.zkey" "$OUT/Verifier.sol"

cat <<EOF

✓ PLONK artifacts ready.
  Public (committed):   $OUT/verification_key.json , $OUT/Verifier.sol
  Proving key (build):  $BUILD/${NAME}_plonk.zkey
  Witness wasm (build): $BUILD/${NAME}_js/${NAME}.wasm

To enable the real backend on the hub:
  export AIMARKET_ZK_BACKEND=plonk
  export AIMARKET_ZK_WASM=$ROOT/$BUILD/${NAME}_js/${NAME}.wasm
  export AIMARKET_ZK_ZKEY=$ROOT/$BUILD/${NAME}_plonk.zkey
  export AIMARKET_ZK_VKEY_JSON=$ROOT/$OUT/verification_key.json
  # drop AIMARKET_ZK_SIMULATED — real PLONK takes over
EOF
