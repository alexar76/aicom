#!/usr/bin/env bash
# Multi-party Groth16 ceremony coordinator — wraps contracts/zk/scripts/setup.sh
# and documents contributor attestation steps. See contracts/zk/ZK_CEREMONY.md.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ZK="$ROOT/contracts/zk"
MIN_CONTRIBUTORS="${ZK_CEREMONY_MIN_CONTRIBUTORS:-3}"

echo "=== AIMarket ZK ceremony coordinator ==="
echo "Minimum contributors: $MIN_CONTRIBUTORS"
echo ""

if ! command -v node >/dev/null 2>&1; then
  echo "ERROR: node.js required (snarkjs)" >&2
  exit 1
fi
if ! command -v snarkjs >/dev/null 2>&1; then
  echo "Installing snarkjs globally..."
  npm install -g snarkjs@0.7.5 circomlibjs@0.1.7
fi

PHASE="${1:-compile}"
case "$PHASE" in
  compile)
    echo "Phase 1: compile circuit + initial zkey (coordinator only — NOT for mainnet alone)"
    bash "$ZK/scripts/setup.sh"
    ;;
  contribute)
    CONTRIB_NAME="${2:-contributor-$(date +%Y%m%d)}"
    IN_ZKEY="${3:-$ZK/build/input_validity_0000.zkey}"
    OUT_ZKEY="$ZK/build/input_validity_0001.zkey"
    if [[ ! -f "$IN_ZKEY" ]]; then
      echo "ERROR: input zkey missing: $IN_ZKEY (run: $0 compile)" >&2
      exit 1
    fi
    echo "Phase 2: contributor '$CONTRIB_NAME'"
    ENTROPY="$(openssl rand -hex 32)"
    snarkjs zkey contribute "$IN_ZKEY" "$OUT_ZKEY" "$CONTRIB_NAME" "$ENTROPY" -v
    echo ""
    echo "Attestation: publish SHA256 of $OUT_ZKEY and destroy local entropy."
    sha256sum "$OUT_ZKEY"
    ;;
  export)
    ZKEY="${2:-$ZK/build/input_validity_0001.zkey}"
    mkdir -p "$ZK/verifier" "$ZK/build"
    snarkjs zkey export verificationkey "$ZKEY" "$ZK/build/verification_key.json"
    snarkjs zkey export solidityverifier "$ZKEY" "$ZK/verifier/Verifier.sol"
    echo "Exported verification_key.json and Verifier.sol"
    ;;
  install-secrets)
    DEST="${AIFACTORY_DATA_ROOT:-$ROOT/data}/secrets/zk"
    mkdir -p "$DEST"
    cp -f "$ZK/build/input_validity_js/input_validity.wasm" "$DEST/input_validity.wasm" 2>/dev/null \
      || cp -f "$ZK/build/input_validity.wasm" "$DEST/" 2>/dev/null || true
    cp -f "$ZK/build/input_validity_0001.zkey" "$DEST/input_validity_0001.zkey"
    cp -f "$ZK/build/verification_key.json" "$DEST/../contracts_zk_verification_key.json" 2>/dev/null || true
    echo "Installed wasm+zkey to $DEST"
    ;;
  verify)
    bash "$ROOT/scripts/verify_zk_artifacts.sh"
    ;;
  *)
    echo "Usage: $0 {compile|contribute [name] [in.zkey]|export [zkey]|install-secrets|verify}"
    exit 2
    ;;
esac
