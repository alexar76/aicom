# ZK Verifier — generated artifacts

This directory is populated by `scripts/setup.sh` after the trusted setup
ceremony. Do NOT hand-edit these files.

**Expected after ceremony:**

| File | Source | Commit? |
|------|--------|---------|
| `Verifier.sol` | `snarkjs zkey export solidityverifier` | Yes |
| `verification_key.json` | `snarkjs zkey export verificationkey` | Yes |

**Never commit:**

| File | Reason |
|------|--------|
| `build/*.zkey` | Proving key — private to operator |
| `build/*.wasm` | Witness generator — private to operator |

See [ZK_CEREMONY.md](../ZK_CEREMONY.md) for the full multi-party ceremony guide.
