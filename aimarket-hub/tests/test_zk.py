"""Tests for ZK-proof verification module (simulated)."""

import tempfile
from pathlib import Path

import pytest

from aimarket_hub.signing import Signer
from aimarket_hub.zk_proofs import ZKInputProof, ZKOutputProof, ZKProver


@pytest.fixture(autouse=True)
def _opt_in_simulated_zk(monkeypatch):
    """Opt in to the development ZK simulation for all tests in this file."""
    monkeypatch.setenv("AIMARKET_ZK_SIMULATED", "1")


@pytest.fixture
def signer():
    with tempfile.TemporaryDirectory() as tmp:
        yield Signer(Path(tmp) / "key")


@pytest.fixture
def prover(signer):
    return ZKProver(signer)


class TestZKInputProof:
    def test_prove_input(self, prover):
        schema = {"type": "object", "properties": {"text": {"type": "string"}}}
        proof = prover.prove_input("cap@v1", schema, {"text": "hello"})
        assert proof.proof_id
        assert proof.input_commitment
        assert proof.nullifier
        assert proof.signature

    def test_verify_valid_input_proof(self, prover):
        schema = {"type": "object", "properties": {"text": {"type": "string"}}}
        import hashlib, json
        schema_hash = hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest()

        proof = prover.prove_input("cap@v1", schema, {"text": "hello"})
        result = prover.verify_input_proof(proof, schema_hash, "cap@v1", prover.signer.public_key_b64)
        assert result["valid"]
        assert "without being revealed" in result["reason"]

    def test_verify_rejects_wrong_schema_hash(self, prover):
        schema = {"type": "object"}
        proof = prover.prove_input("cap@v1", schema, {"text": "hello"})
        result = prover.verify_input_proof(proof, "wrong_hash", "cap@v1", prover.signer.public_key_b64)
        assert not result["valid"]
        assert "mismatch" in result["reason"]

    def test_verify_rejects_wrong_capability(self, prover):
        schema = {"type": "object", "properties": {"text": {"type": "string"}}}
        import hashlib, json
        schema_hash = hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest()

        proof = prover.prove_input("cap@v1", schema, {"text": "hello"})
        result = prover.verify_input_proof(proof, schema_hash, "other_cap@v1", prover.signer.public_key_b64)
        assert not result["valid"]


class TestZKOutputProof:
    def test_prove_output(self, prover):
        proof = prover.prove_output("inv_001", "cap@v1", "input_hash_abc",
                                     {"text": "hello"}, {"result": "bonjour"})
        assert proof.proof_id
        assert proof.output_commitment
        assert proof.signature

    def test_verify_valid_output_proof(self, prover):
        proof = prover.prove_output("inv_001", "cap@v1", "commit_abc",
                                     {"text": "hello"}, {"result": "bonjour"})
        result = prover.verify_output_proof(proof, "commit_abc", "cap@v1", prover.signer.public_key_b64)
        assert result["valid"]

    def test_verify_rejects_wrong_input_commitment(self, prover):
        proof = prover.prove_output("inv_001", "cap@v1", "commit_abc",
                                     {"text": "hello"}, {"result": "bonjour"})
        result = prover.verify_output_proof(proof, "wrong_commitment", "cap@v1", prover.signer.public_key_b64)
        assert not result["valid"]


class TestZKFlow:
    def test_private_invoke_flow(self, prover):
        def executor(pid, cid, inp):
            return {"output": f"executed {cid}"}

        schema = {"type": "object", "properties": {"text": {"type": "string"}}}
        result = prover.private_invoke_flow("cap@v1", "p1", schema, {"text": "secret"}, executor)

        assert result["success"]
        assert result["input_proof"]["verified"]
        assert result["output_proof"]["verified"]
        # Privacy guarantees deliberately set to False — this is a simulation,
        # not real ZK. Caller must check "simulated" flag before trusting privacy.
        assert result["simulated"] is True
        assert result["privacy_guarantees"]["input_hidden"] is False
        assert result["privacy_guarantees"]["double_spend_protected"] is False
        assert "warning" in result

    def test_stats(self, prover):
        s = prover.stats()
        assert "nullifiers_used" in s
        assert "zk_scheme" in s
        assert s["simulated"] is True

    def test_opt_in_required(self, monkeypatch):
        """ZKProverSimulated must refuse to instantiate without explicit opt-in."""
        from aimarket_hub.zk_proofs import ZKProverSimulated
        monkeypatch.delenv("AIMARKET_ZK_SIMULATED", raising=False)
        import pytest
        with pytest.raises(RuntimeError, match="simulation, not real ZK"):
            ZKProverSimulated()
