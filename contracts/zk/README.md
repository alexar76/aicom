# AIMarket ZK — Real PLONK Backend (Groth16 optional)

This replaces the development-only `ZKProverSimulated` (in
`aimarket-hub/aimarket_hub/zk_proofs.py`) with a real proving pipeline using
circom circuits, the snarkjs prover, and an on-chain Solidity verifier.

**The default and deployed backend is PLONK** (universal structured reference
string — the Hermez powers-of-tau — so there is **no per-circuit trusted-setup
ceremony**). A Groth16 path is also supported as an option (smaller/cheaper
proofs, but it requires a per-circuit multi-party ceremony — see
[ZK_CEREMONY.md](ZK_CEREMONY.md)).

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
├── scripts/setup_plonk.sh            ← PLONK setup (default · universal · no ceremony)
├── scripts/setup.sh                  ← Groth16 setup (optional · needs ceremony)
├── verifier/Verifier.sol             ← auto-generated PlonkVerifier, deploy this
├── verifier/verification_key.json    ← auto-generated, public ("protocol": "plonk")
├── package.json                      ← circomlib npm dep
└── build/                            ← snarkjs output (gitignored)
    ├── input_validity.r1cs
    ├── input_validity.wasm
    └── input_validity_plonk.zkey     ← PLONK proving key (public for PLONK)
```

## One-time setup (operator)

PLONK uses a **universal** SRS (the public Hermez powers-of-tau), so there is
**no per-circuit ceremony and no per-circuit toxic waste**.

```bash
# 1. Install tools
curl -L https://docs.circom.io/install/ | sh        # circom
npm install -g snarkjs                              # snarkjs CLI
pip install poseidon-py                             # Python Poseidon for witness gen

# 2. Install circomlib (Poseidon, Num2Bits, etc.)
cd contracts/zk
npm install

# 3. PLONK setup (default)
npm run setup            # = bash scripts/setup_plonk.sh
```

After setup completes:

```
contracts/zk/verifier/Verifier.sol           ← PlonkVerifier — deploy to chain
contracts/zk/verifier/verification_key.json  ← commit to git ("protocol": "plonk")
contracts/zk/build/input_validity_plonk.zkey ← PLONK proving key (public)
contracts/zk/build/input_validity_js/        ← witness generator (WASM)
```

> **Groth16 (optional):** `npm run setup:groth16` (= `scripts/setup.sh`) instead.
> Groth16 gives smaller on-chain proofs but its per-circuit zkey embeds toxic
> waste, so it is only safe with a **multi-party ceremony** (≥3 unrelated
> contributors) — see [ZK_CEREMONY.md](ZK_CEREMONY.md). The generated verifier is
> then a `Groth16Verifier` (renamed to `AIMarketInputValidityVerifier`).

## Deploy the on-chain verifier

```bash
cd contracts/zk
forge create verifier/Verifier.sol:PlonkVerifier \
    --rpc-url https://mainnet.base.org \
    --private-key $DEPLOYER_KEY --broadcast
```

Set the resulting address in your hub `.env`:

```
AIMARKET_ZK_VERIFIER_CONTRACT=0xDeployedVerifier
```

## Wire the hub to real ZK

```bash
# Hub .env
AIMARKET_ZK_BACKEND=plonk          # default backend; matches the deployed PlonkVerifier
AIMARKET_ZK_WASM=/path/to/contracts/zk/build/input_validity_js/input_validity.wasm
AIMARKET_ZK_ZKEY=/path/to/contracts/zk/build/input_validity_plonk.zkey
AIMARKET_ZK_VKEY_JSON=/path/to/contracts/zk/verifier/verification_key.json

# Optional — only used when verifying proofs on-chain (off-chain by default)
AIMARKET_ZK_VERIFIER_CONTRACT=0xDeployedVerifier

# CRITICAL: drop the dev simulation guard
# AIMARKET_ZK_SIMULATED=1     ← remove this line
```

`aimarket_hub.zk_groth16.make_zk_prover()` returns a real prover when
`AIMARKET_ZK_BACKEND` is set to `plonk` (default backend) or `groth16`; it
implements the same interface as `ZKProverSimulated`, so the invoke pipeline
transparently switches backends. (With the variable unset it falls back to the
simulated prover — opt-in to real proving by setting the backend.)

## Trust assumptions you are NOT off the hook for

- **PLONK universal SRS.** PLONK reuses the Hermez powers-of-tau (~100
  contributors, generally accepted). There is **no per-circuit ceremony**, but
  verify the SRS provenance and checksums for your own peace of mind.
- **Groth16 (only if you pick that path).** A single-contributor Groth16 zkey is
  cryptographically weak — the contributor's `tau` (toxic waste) lets them forge
  proofs forever. Run a multi-party ceremony (≥3 unrelated contributors) — see
  [ZK_CEREMONY.md](ZK_CEREMONY.md).
- **circom + snarkjs are external dependencies.** Pin versions
  (`package.json` is committed) and verify checksums.
- **The Solidity verifier is auto-generated.** Audit it (the math is
  fixed; what matters is the verification-key values are correct).
- **poseidon-py is a Python re-implementation of Poseidon.** Cross-check
  outputs against a reference implementation (e.g., snarkjs poseidon)
  before trusting it in production.

## Testing the pipeline end-to-end

```bash
# 1. Build (after setup)
cd contracts/zk
npm run setup

# 2. Prove + verify a sample input in Python
export AIMARKET_ZK_BACKEND=plonk
export AIMARKET_ZK_WASM=$(pwd)/build/input_validity_js/input_validity.wasm
export AIMARKET_ZK_ZKEY=$(pwd)/build/input_validity_plonk.zkey
export AIMARKET_ZK_VKEY_JSON=$(pwd)/verifier/verification_key.json

python3 -c '
from aimarket_hub.zk_groth16 import make_zk_prover
p = make_zk_prover()
proof = p.prove_input("test-cap", {"type":"object"}, {"hello":"world"})
print("Proof generated:", proof.input_commitment[:20], "…")
r = p.verify_input_proof(proof, "test-cap", p.signer.public_key_b64)
print("Verify:", r)
assert r["valid"] and not r["simulated"]
print("OK — real PLONK round-trip works")
'
```

If anything fails: setup did not complete, snarkjs isn't on PATH,
or one of the env vars points at the wrong file. Re-run setup or check
paths.

## Deployed on Base mainnet (demo)

The on-chain verifier (`verifier/Verifier.sol` → `PlonkVerifier`) is deployed +
**source-verified on Basescan** (chainId 8453):
[`0xb11af6f387aCD57E6AECDa222D0108e6380ACf65`](https://basescan.org/address/0xb11af6f387aCD57E6AECDa222D0108e6380ACf65),
owned/deployed by the demo wallet `0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a`. Full context +
every transaction: [../../docs/onchain-journal.md](../../docs/onchain-journal.md).

## Networks & RPC
The verifier deploys via `forge create --rpc-url`. Runtime chain readers select their network
and fail over across RPC endpoints through the shared chain registry — default **Base**. See
[../../docs/chain-networks.md](../../docs/chain-networks.md).
