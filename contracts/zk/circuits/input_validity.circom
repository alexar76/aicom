pragma circom 2.1.6;

include "circomlib/circuits/poseidon.circom";
include "circomlib/circuits/comparators.circom";

/*
 * input_validity — minimal Groth16 circuit proving:
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
