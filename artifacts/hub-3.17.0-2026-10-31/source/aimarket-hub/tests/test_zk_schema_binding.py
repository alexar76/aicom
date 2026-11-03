"""The real (PLONK/Groth16) verifier must bind the circuit's `schemaHash` public signal.

`input_validity.circom` computes the nullifier as ``Poseidon(inputValue, schemaHash)`` and
publishes `schemaHash`, which means the PROVER chooses it. Replay protection therefore only
works if the verifier re-derives the expected `schemaHash` from the capability's real schema:
otherwise the same secret input yields an unlimited supply of distinct, individually-valid
nullifiers, and `used_nullifiers` never fires.

These tests run real proofs, so they need the built circuit artifacts and snarkjs; they skip
when either is absent (the simulated backend is covered by test_zk.py).
"""

from __future__ import annotations

import os
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

ZK_DIR = Path(__file__).resolve().parents[2] / "contracts" / "zk"
WASM = ZK_DIR / "build" / "input_validity_js" / "input_validity.wasm"
ZKEY = ZK_DIR / "build" / "input_validity_plonk.zkey"
VKEY = ZK_DIR / "build" / "verification_key.json"
POSEIDON = ZK_DIR / "scripts" / "poseidon2.mjs"
SNARKJS_BIN = ZK_DIR / "node_modules" / ".bin"

CAPABILITY = "legal.review@v1"
REAL_SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}}}
# Any other schema produces a different domain separator — that is the whole attack.
OTHER_SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}}, "extra": 1}
SECRET_INPUT = {"text": "one secret input, spent twice"}


def _artifacts_present() -> bool:
    return all(p.exists() for p in (WASM, ZKEY, VKEY, POSEIDON)) and (
        shutil.which("snarkjs") is not None or (SNARKJS_BIN / "snarkjs").exists()
    )


pytestmark = pytest.mark.skipif(
    not _artifacts_present(),
    reason="built circuit artifacts or snarkjs not available (run contracts/zk/scripts/setup_plonk.sh)",
)


@pytest.fixture
def prover(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMARKET_ZK_WASM", str(WASM))
    monkeypatch.setenv("AIMARKET_ZK_ZKEY", str(ZKEY))
    monkeypatch.setenv("AIMARKET_ZK_VKEY_JSON", str(VKEY))
    monkeypatch.setenv("AIMARKET_ZK_POSEIDON_SCRIPT", str(POSEIDON))
    monkeypatch.setenv("AIMARKET_ZK_BACKEND", "plonk")
    monkeypatch.setenv("PATH", f"{SNARKJS_BIN}{os.pathsep}{os.environ['PATH']}")

    from aimarket_hub.zk_groth16 import Groth16Prover

    return Groth16Prover(nullifier_db=tmp_path / "nullifiers.db")


def test_honest_proof_verifies_and_replay_is_caught(prover):
    proof = prover.prove_input(CAPABILITY, REAL_SCHEMA, SECRET_INPUT)

    first = prover.verify_input_proof(
        proof, CAPABILITY, prover.signer.public_key_b64, REAL_SCHEMA
    )
    assert first["valid"], first["reason"]
    assert first["simulated"] is False

    second = prover.verify_input_proof(
        proof, CAPABILITY, prover.signer.public_key_b64, REAL_SCHEMA
    )
    assert not second["valid"]
    assert "replay" in second["reason"].lower()


def test_real_proof_cannot_replay_under_a_resigned_envelope_nullifier(prover):
    proof = prover.prove_input(CAPABILITY, REAL_SCHEMA, SECRET_INPUT)
    assert prover.verify_input_proof(
        proof, CAPABILITY, prover.signer.public_key_b64, REAL_SCHEMA
    )["valid"]
    forged = replace(proof, nullifier="1" if proof.nullifier != "1" else "2")
    forged.sign(prover.signer)
    result = prover.verify_input_proof(
        forged, CAPABILITY, prover.signer.public_key_b64, REAL_SCHEMA
    )
    assert not result["valid"] and "envelope" in result["reason"].lower()
    assert prover._nullifiers.count() == 1


def test_forged_schema_hash_cannot_mint_a_second_nullifier(prover):
    """The double-spend the schemaHash binding exists to stop.

    Both proofs commit to the SAME secret input and both are cryptographically valid — they
    differ only in a public signal. Without the binding the second one sails past the
    nullifier store, because its nullifier is genuinely unseen.
    """
    honest = prover.prove_input(CAPABILITY, REAL_SCHEMA, SECRET_INPUT)
    assert prover.verify_input_proof(
        honest, CAPABILITY, prover.signer.public_key_b64, REAL_SCHEMA
    )["valid"]

    forged = prover.prove_input(CAPABILITY, OTHER_SCHEMA, SECRET_INPUT)
    forged.capability_id = CAPABILITY          # envelope still names the expected capability
    forged.sign(prover.signer)                 # and the hub signs its own envelope
    assert forged.nullifier != honest.nullifier, "a fresh nullifier is what makes this an attack"

    # The proof really is valid — checked by verifying it against the schema it was built
    # with, which is exactly what an unbound verifier would effectively be doing.
    assert prover.verify_input_proof(
        forged, CAPABILITY, prover.signer.public_key_b64, OTHER_SCHEMA
    )["valid"], "expected the forged proof to be cryptographically sound"

    # Bound to the capability's declared schema, it is refused.
    bound = prover.verify_input_proof(
        forged, CAPABILITY, prover.signer.public_key_b64, REAL_SCHEMA
    )
    assert not bound["valid"]
    assert "schemahash" in bound["reason"].lower()


def test_verifier_refuses_when_no_schema_is_supplied(prover):
    """Fail closed, mirroring how an empty `prover_public_key` is treated."""
    proof = prover.prove_input(CAPABILITY, REAL_SCHEMA, SECRET_INPUT)
    result = prover.verify_input_proof(proof, CAPABILITY, prover.signer.public_key_b64)
    assert not result["valid"]
    assert "expected_input_schema" in result["reason"]


def test_schema_hash_is_bound_to_the_capability_too(prover):
    """Same schema, different capability must not share a nullifier."""
    a = prover._derive_schema_hash(REAL_SCHEMA, CAPABILITY)
    b = prover._derive_schema_hash(REAL_SCHEMA, "other.cap@v1")
    assert a != b
