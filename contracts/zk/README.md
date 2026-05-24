# AIMarket ZK — Real Groth16 Backend

This replaces the development-only `ZKProverSimulated` (in
`aimarket-hub/aimarket_hub/zk_proofs.py`) with a real Groth16 proving
pipeline using circom circuits, snarkjs prover, and an on-chain
Solidity verifier.

## What this proves

The `input_validity` circuit proves the **prover knows an input** that
hashes to a published commitment and produces a deterministic nullifier
from `(input, schemaHash, capabilityId)` — without revealing the input.

```
Public:   inputCommitment, nullifier, schemaHash
Private:  inputValue, nullifierSalt

Constraint 1: inputValue < 2^252                          (range check)
Constraint 2: Poseidon(inputValue, nullifierSalt) == inputCommitment
Constraint 3: Poseidon(inputValue, schemaHash)    == nullifier
```

## What this does NOT prove

- **Arbitrary JSON-schema validity.** The caller has to encode their
  input into a single field element first (typically by SHA-256 →
  truncating to 248 bits). A real "schema-conformance" proof needs a
  per-schema circuit compiled from the JSON Schema (out of scope for
  this skeleton — research project, not an evening's work).
- **Execution correctness.** Output proofs would need a second circuit
  proving `output == f(input)` for capability-specific `f`. Currently
  outputs are just signed by the provider (see `signing.py`).

## Files

```
contracts/zk/
├── circuits/input_validity.circom    ← the circuit
├── scripts/setup.sh                  ← one-time trusted setup
├── verifier/Verifier.sol             ← auto-generated, deploy this
├── verifier/verification_key.json    ← auto-generated, public
├── package.json                      ← circomlib npm dep
└── build/                            ← snarkjs output (gitignored)
    ├── input_validity.r1cs
    ├── input_validity.wasm
    └── input_validity_0001.zkey      ← prover artifact (KEEP PRIVATE)
```

## One-time setup (operator)

```bash
# 1. Install tools
curl -L https://docs.circom.io/install/ | sh        # circom
npm install -g snarkjs                              # snarkjs CLI
pip install poseidon-py                             # Python Poseidon for witness gen

# 2. Install circomlib (Poseidon, Num2Bits, etc.)
cd contracts/zk
npm install

# 3. Run trusted setup
./scripts/setup.sh
# Follow the prompts. Adds randomness; for a real prod system invite
# multiple unrelated parties to contribute (each running `snarkjs
# groth16 contribute` against the previous zkey).
```

After setup completes:

```
contracts/zk/verifier/Verifier.sol           ← deploy to chain
contracts/zk/verifier/verification_key.json  ← commit to git
contracts/zk/build/input_validity_0001.zkey  ← keep in operator secrets
contracts/zk/build/input_validity_js/        ← witness generator (WASM)
```

## Deploy the on-chain verifier

```bash
cd contracts/zk
forge create verifier/Verifier.sol:AIMarketInputValidityVerifier \
    --rpc-url https://mainnet.base.org \
    --ledger --mnemonic-derivation-path "m/44'/60'/0'/0/0" \
    --sender 0xYourDeployerAddress
```

Set the resulting address in your hub `.env`:

```
AIMARKET_ZK_VERIFIER_CONTRACT=0xDeployedVerifier
```

## Wire the hub to real ZK

```bash
# Hub .env
AIMARKET_ZK_BACKEND=groth16
AIMARKET_ZK_WASM=/path/to/contracts/zk/build/input_validity_js/input_validity.wasm
AIMARKET_ZK_ZKEY=/path/to/contracts/zk/build/input_validity_0001.zkey
AIMARKET_ZK_VKEY_JSON=/path/to/contracts/zk/verifier/verification_key.json

# Optional — only used when verifying proofs on-chain (off-chain by default)
AIMARKET_ZK_VERIFIER_CONTRACT=0xDeployedVerifier

# CRITICAL: drop the dev simulation guard
# AIMARKET_ZK_SIMULATED=1     ← remove this line
```

`aimarket_hub.zk_groth16.make_zk_prover()` returns a `Groth16Prover`
when `AIMARKET_ZK_BACKEND=groth16` is set. It implements the same
interface as `ZKProverSimulated` so the invoke pipeline transparently
switches backends.

## Trust assumptions you are NOT off the hook for

- **Trusted setup is multi-party.** A single-contributor zkey is
  cryptographically weak — the contributor's `tau` (toxic waste) lets
  them forge proofs forever. For mainnet, run a multi-party ceremony
  (see [snarkjs contribute](https://github.com/iden3/snarkjs#groth16))
  with at least 3 unrelated contributors who publicly attest to
  destroying their entropy.
- **Powers of Tau is reused from the Hermez ceremony.** That ceremony
  had ~100 contributors and is generally accepted. Verify its
  provenance for your own peace of mind.
- **circom + snarkjs are external dependencies.** Pin versions
  (`package.json` is committed) and verify checksums.
- **The Solidity verifier is auto-generated.** Audit it (the math is
  fixed; what matters is the verification key values are correct).
- **poseidon-py is a Python re-implementation of Poseidon.** Cross-check
  outputs against a reference implementation (e.g., snarkjs poseidon)
  before trusting it in production.

## Testing the pipeline end-to-end

```bash
# 1. Build (after setup.sh has run)
cd contracts/zk
./scripts/setup.sh

# 2. Prove + verify a sample input in Python
export AIMARKET_ZK_BACKEND=groth16
export AIMARKET_ZK_WASM=$(pwd)/build/input_validity_js/input_validity.wasm
export AIMARKET_ZK_ZKEY=$(pwd)/build/input_validity_0001.zkey
export AIMARKET_ZK_VKEY_JSON=$(pwd)/verifier/verification_key.json

python3 -c '
from aimarket_hub.zk_groth16 import make_zk_prover
p = make_zk_prover()
proof = p.prove_input("test-cap", {"type":"object"}, {"hello":"world"})
print("Proof generated:", proof.input_commitment[:20], "…")
r = p.verify_input_proof(proof, "test-cap", p.signer.public_key_b64)
print("Verify:", r)
assert r["valid"] and not r["simulated"]
print("OK — real Groth16 round-trip works")
'
```

If anything fails: setup.sh did not complete, snarkjs isn't on PATH,
or one of the env vars points at the wrong file. Re-run setup or check
paths.
