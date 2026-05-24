# Groth16 Trusted Setup Ceremony

## Why a ceremony?

Groth16 proving keys embed a "toxic waste" parameter — if the randomness used to
generate the initial zkey is ever recovered, an attacker can forge proofs that
pass verification. The **only** way to trust the zkey is through a multi-party
computation (MPC) ceremony where at least **one** participant honestly destroys
their entropy. This is the "1-out-of-N" trust model.

A **single-operator setup** (one contribution) provides **minimum security**:
the operator's randomness is the single point of failure. This is acceptable
only for devnet/testnet.

For **production mainnet**, you MUST run at least **3 contributors** from
unrelated parties (different organizations, no shared infrastructure).

## Quick start (single-operator, dev)

```bash
cd contracts/zk
npm install circomlib
bash scripts/setup.sh
```

This runs the full pipeline: compile → ptau → zkey → verify → export → Solidity
verifier. The operator provides one entropy contribution.

## Multi-party production ceremony

### Step 1: Coordinator starts the ceremony

```bash
cd contracts/zk
npm install circomlib

# Phase 1: compile circuit + download ptau
PTAU_POWER=14 bash scripts/setup.sh --phase1-only

# This produces build/input_validity_0000.zkey (initial, no contributions yet)
```

### Step 2: Contributor N adds entropy

Each contributor runs:

```bash
# Receive build/input_validity_NNNN.zkey from the coordinator
# (transmitted over a secure channel — PGP, Signal, air-gapped machine)

snarkjs groth16 contribute input_validity_NNNN.zkey input_validity_NNN1.zkey \
    --name="contributor-alias-$(date +%Y%m%d)" -v

# Contributor sends input_validity_NNN1.zkey back to coordinator
# Contributor MUST destroy their entropy (do NOT keep a copy of randomness)
```

The contributor SHOULD:
- Sign the contribution hash with a public key (PGP, SSH, Ethereum address)
- Post the contribution hash publicly (Twitter, GitHub Gist) — this creates
  accountability and allows independent verification
- Run on an air-gapped or freshly-booted machine if possible

### Step 3: Apply a random beacon (optional but recommended)

After all human contributors, apply a public random beacon to prevent any
contributor from faking the ceremony transcript:

```bash
# Bitcoin block hash as a public entropy source
BEACON_HASH=$(curl -s https://blockchain.info/latestblock | jq -r '.hash')
echo "$BEACON_HASH" | snarkjs groth16 beacon input_validity_NNNN.zkey \
    input_validity_final.zkey "$BEACON_HASH" 10
```

### Step 4: Coordinator finalizes

```bash
# Verify final zkey
snarkjs zkey verify input_validity.r1cs pot14_final.ptau input_validity_final.zkey

# Export verification key
snarkjs zkey export verificationkey input_validity_final.zkey verifier/verification_key.json

# Generate Solidity verifier
snarkjs zkey export solidityverifier input_validity_final.zkey verifier/Verifier.sol

# Commit PUBLIC artifacts to git:
#   verifier/Verifier.sol
#   verifier/verification_key.json
#
# NEVER commit build/input_validity_final.zkey — it is operator-private.
```

## Deployment checklist

- [ ] At least 3 unrelated contributors added entropy (prod only)
- [ ] Each contributor signed and published their contribution hash
- [ ] Random beacon applied (Bitcoin block or similar)
- [ ] `verifier/Verifier.sol` deployed to target chain
- [ ] `verifier/verification_key.json` distributed to all verifier nodes
- [ ] `AIMARKET_ZK_VERIFIER_CONTRACT=0x...` set in hub .env
- [ ] `AIMARKET_ZK_SIMULATED=0` set (disable simulation mode)
- [ ] Proving key (`build/*.zkey`) stored securely, NEVER in git

## Security model

| Deployment | Min contributors | Security guarantee |
|------------|-----------------|--------------------|
| Devnet     | 1 (operator)    | None — proofs forgeable if operator compromised |
| Testnet    | 1 (operator)    | Weak — acceptable for valueless transactions |
| Mainnet    | 3+ (unrelated)  | Strong — requires ALL 3+ to collude or be compromised |

The **proving key is operator-private**. Only the operator needs it to generate
proofs. All other parties (verifiers, clients, contracts) only need the public
`verification_key.json`.

## Expected costs

| Operation | Gas (EVM) | CU (Solana) |
|-----------|-----------|-------------|
| `verifyProof(uint[2], uint[2][2], uint[2])` | ~230k | ~10k |

Verification is invoked once per capability invocation with private input.
