pragma circom 2.1.6;

include "circomlib/circuits/poseidon.circom";
include "circomlib/circuits/comparators.circom";

/*
 * input_validity — minimal circuit (PLONK by default, Groth16 optional) proving:
 *
 *   1. The prover knows a secret `input` (a single field-element).
 *   2. Poseidon(input, nullifierSalt) == inputCommitment  (binding)
 *   3. Poseidon(input, schemaHash)    == nullifier        (replay protection)
 *   4. 0 <= input < 2^252                                 (range check —
 *      keeps proofs inside the BN254 scalar field; bigger inputs must be
 *      split or hashed first).
 *
 * Public inputs (in order): inputCommitment, nullifier, schemaHash
 * Private inputs:            input, nullifierSalt
 *
 * What this REALLY proves (in plain English):
 *   "I know an input that, when combined with this schema, produces a
 *    commitment I'm publishing now, and a unique nullifier that hubs can
 *    use to detect double-spend. I am NOT telling you the input."
 *
 * What this does NOT prove:
 *   - That the input matches a complex JSON schema (would need a circuit
 *     compiled from that schema; this minimal version assumes inputs are
 *     pre-encoded as a single field element by the caller).
 *   - Correct execution of the capability (output proof needs a separate
 *     circuit — see roadmap, this is the input-side gate only).
 *   - That `schemaHash` is the RIGHT schema. It is a public input, so the
 *     PROVER picks it, and the circuit only asserts the nullifier is
 *     consistent with whatever was picked.
 *
 * VERIFIER OBLIGATION — `schemaHash` must be pinned off-circuit.
 *   Because `nullifier == Poseidon(input, schemaHash)`, a prover who is free
 *   to vary `schemaHash` gets a different — and therefore unseen — nullifier
 *   for the SAME secret input, as often as it likes. A verifier that only
 *   checks "is this nullifier new?" then accepts the same input forever, and
 *   the replay protection above is decorative. Checking a `capability_id`
 *   carried NEXT TO the proof does not help: that is metadata, not one of the
 *   signals this circuit constrained.
 *   So every verifier MUST re-derive the expected `schemaHash` from the
 *   capability's declared schema and compare it to public signal [2], and
 *   must refuse the proof when it has no schema to derive from.
 *   Reference implementation: `Groth16Prover._derive_schema_hash` /
 *   `verify_input_proof` step 3 in `aimarket-hub/aimarket_hub/zk_groth16.py`;
 *   regression tests in `aimarket-hub/tests/test_zk_schema_binding.py`.
 *
 * Build / setup / prove / verify:  see contracts/zk/README.md
 */

template InputValidity() {
    // ── Public signals ──────────────────────────────
    signal input  inputCommitment;
    signal input  nullifier;
    signal input  schemaHash;

    // ── Private witness ─────────────────────────────
    signal input  inputValue;
    signal input  nullifierSalt;

    // ── Constraint 1: range check on inputValue (252 bits) ──
    component bits = Num2Bits(252);
    bits.in <== inputValue;

    // ── Constraint 2: commitment = Poseidon(input, salt) ──
    component commitHash = Poseidon(2);
    commitHash.inputs[0] <== inputValue;
    commitHash.inputs[1] <== nullifierSalt;
    commitHash.out === inputCommitment;

    // ── Constraint 3: nullifier = Poseidon(input, schemaHash) ──
    component nullHash = Poseidon(2);
    nullHash.inputs[0] <== inputValue;
    nullHash.inputs[1] <== schemaHash;
    nullHash.out === nullifier;
}

component main {public [inputCommitment, nullifier, schemaHash]} = InputValidity();
