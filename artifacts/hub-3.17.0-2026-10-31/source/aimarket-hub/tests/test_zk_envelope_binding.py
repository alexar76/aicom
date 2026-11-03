"""Exercise real-backend envelope/replay guards without circuit build artifacts.

The snarkjs boundary is stubbed successful; these tests verify that even a
cryptographically accepted proof cannot bypass its signed public-signal binding.
Actual proof/circuit checks remain in test_zk_schema_binding.py.
"""
from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from aimarket_hub.signing import Signer
from aimarket_hub.zk_groth16 import Groth16Proof, Groth16Prover, _BN254_R, _NullifierStore


@pytest.fixture
def verifier(tmp_path, monkeypatch):
    prover = Groth16Prover.__new__(Groth16Prover)
    prover.signer = Signer(key_path=str(tmp_path / "signing-key"))
    prover._system = "plonk"
    prover._snarkjs = "snarkjs-test-boundary"
    prover.vkey = tmp_path / "verification_key.json"
    prover._nullifiers = _NullifierStore(tmp_path / "nullifiers.db")
    monkeypatch.setattr(prover, "_derive_schema_hash", lambda schema, capability: 7)
    calls = []

    def verified(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="OK", stderr="")

    monkeypatch.setattr("aimarket_hub.zk_groth16.subprocess.run", verified)
    return prover, calls


def envelope(prover, *, commitment="3", nullifier="5"):
    return Groth16Proof(proof={"test": "accepted at stub boundary"},
                        public_signals=[commitment, nullifier, "7"],
                        input_commitment=commitment, nullifier=nullifier,
                        schema_hash="7", capability_id="bound.test@v1").sign(prover.signer)


def verify(prover, proof):
    return prover.verify_input_proof(proof, "bound.test@v1", prover.signer.public_key_b64, {})


def test_canonical_bound_proof_consumes_exact_nullifier_and_blocks_replay(verifier):
    prover, calls = verifier
    proof = envelope(prover)
    assert verify(prover, proof)["valid"]
    assert prover._nullifiers.contains("5")
    assert not verify(prover, proof)["valid"]
    assert len(calls) == 1


@pytest.mark.parametrize("index", range(3))
def test_public_signal_swap_cannot_reuse_signed_envelope(verifier, index):
    prover, calls = verifier
    proof = envelope(prover)
    # The signature still verifies: public_signals is not part of canonical().
    proof.public_signals[index] = "11"
    assert prover.signer.verify(prover.signer.public_key_b64, proof.signature, proof.canonical())
    result = verify(prover, proof)
    assert not result["valid"] and "envelope" in result["reason"].lower()
    assert not calls and prover._nullifiers.count() == 0


def test_resigned_metadata_cannot_spend_same_proof_under_fresh_nullifier(verifier):
    prover, calls = verifier
    proof = envelope(prover)
    assert verify(prover, proof)["valid"]
    forged = copy.deepcopy(proof)
    forged.nullifier = "11"
    forged.sign(prover.signer)
    assert not verify(prover, forged)["valid"]
    assert len(calls) == 1 and not prover._nullifiers.contains("11")


@pytest.mark.parametrize("bad", ["05", "+5", "-5", "5.0", " 5", "٥", "", str(_BN254_R), "9" * 79, 5, True, None])
def test_noncanonical_field_aliases_cannot_create_fresh_replay_keys(verifier, bad):
    prover, calls = verifier
    proof = envelope(prover, nullifier=bad)
    assert not verify(prover, proof)["valid"]
    assert not calls and prover._nullifiers.count() == 0


@pytest.mark.parametrize("signals", [[], ["3"], ["3", "5"], ["3", "5", "7", "11"], None])
def test_malformed_signal_shape_fails_closed(verifier, signals):
    prover, calls = verifier
    proof = envelope(prover)
    proof.public_signals = signals
    assert not verify(prover, proof)["valid"]
    assert not calls


def test_malformed_dict_envelope_fails_closed(verifier):
    prover, calls = verifier
    assert not verify(prover, {"proof": {}, "public_signals": []})["valid"]
    assert not calls
