"""ZK-Proof simulation — DEVELOPMENT ONLY (fail-loud opt-in required).

⚠️  THIS IS NOT ZERO-KNOWLEDGE.

This module provides signed SHA-256 commitments dressed in ZK terminology.
It does NOT hide inputs, does NOT prove computation, and provides
NO cryptographic guarantees beyond Ed25519 signatures on hashes.

It exists only for:
  1. Local development against the ZK API shape
  2. Testing the invoke flow without setting up real circuit infrastructure

To prevent accidental production use, the prover/verifier raises
RuntimeError unless `AIMARKET_ZK_SIMULATED=1` is explicitly set.

For real ZK (Groth16/PLONK), integrate circom + bellman or gnark.
The interface here is intentionally compatible so a real backend can
drop in without API churn.

Every output dict carries `"simulated": true` so downstream consumers
cannot mistake these for real proofs.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from aimarket_hub.signing import Signer

logger = logging.getLogger(__name__)


def _require_simulated_opt_in() -> None:
    """Fail-loud unless operator has explicitly acknowledged simulation."""
    if os.environ.get("AIMARKET_ZK_SIMULATED", "").strip() != "1":
        raise RuntimeError(
            "ZKProver is a development simulation, not real ZK. "
            "To use it in dev/test, set AIMARKET_ZK_SIMULATED=1. "
            "For production, integrate a real Groth16/PLONK backend "
            "(circom + bellman/gnark) — see contracts/zk/ for the interface."
        )


@dataclass
class ZKInputProof:
    """ZK proof that input matches the capability's JSON Schema without revealing it."""

    proof_id: str
    capability_id: str
    schema_hash: str  # SHA-256 of the input_schema
    input_commitment: str  # Pedersen commitment to the input
    nullifier: str  # Prevents double-use
    proof_bytes: str  # Simulated Groth16 proof
    public_signals: list[str]  # Public inputs to the circuit
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    signature: str = ""

    def canonical(self) -> str:
        return (
            f"proof_id:{self.proof_id}"
            f"|capability:{self.capability_id}"
            f"|schema_hash:{self.schema_hash}"
            f"|commitment:{self.input_commitment}"
            f"|nullifier:{self.nullifier}"
        )

    def sign(self, signer: Signer) -> "ZKInputProof":
        self.signature = signer.sign_canonical(self.canonical())
        return self


@dataclass
class ZKOutputProof:
    """ZK proof that output is the correct result of executing the capability."""

    proof_id: str
    invocation_id: str
    capability_id: str
    input_commitment: str  # Matches the input proof commitment
    output_commitment: str  # Commitment to the output
    proof_bytes: str  # Simulated Groth16 proof
    public_signals: list[str]
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    signature: str = ""

    def canonical(self) -> str:
        return (
            f"proof_id:{self.proof_id}"
            f"|invocation:{self.invocation_id}"
            f"|input_commitment:{self.input_commitment}"
            f"|output_commitment:{self.output_commitment}"
        )

    def sign(self, signer: Signer) -> "ZKOutputProof":
        self.signature = signer.sign_canonical(self.canonical())
        return self


class ZKProverSimulated:
    """SIMULATED ZK proof generator — NOT real zero-knowledge.

    This class produces signed SHA-256 commitments and labels them "ZK proofs".
    It exists for local development and API-shape testing only.

    Real Groth16 / PLONK requires:
      - circom or gnark circuit compilation
      - Trusted setup (Groth16) or universal setup (PLONK)
      - bellman/arkworks/gnark prover/verifier libraries
      - Significant gas + verification cost on-chain

    To use this development simulation, opt in:
        export AIMARKET_ZK_SIMULATED=1

    Without that env var, instantiation raises RuntimeError to prevent
    accidental production use.

    Every output dict from this class carries `"simulated": True` and
    `"warning": "..."` fields so consumers cannot mistake the result
    for a real ZK proof.
    """

    def __init__(self, signer: Signer | None = None):
        _require_simulated_opt_in()
        self.signer = signer or Signer()
        self._used_nullifiers: set[str] = set()  # Prevent double-proofs
        logger.warning(
            "ZKProverSimulated initialized — output is NOT real ZK. "
            "Set AIMARKET_ZK_SIMULATED=0 in production."
        )

    @staticmethod
    def _mark_simulated(d: dict[str, Any]) -> dict[str, Any]:
        """Stamp every returned dict so callers cannot mistake it for real ZK."""
        d["simulated"] = True
        d.setdefault(
            "warning",
            "This is a development simulation, not a real ZK proof. "
            "Output proves nothing about input/computation privacy.",
        )
        return d

    # ── Input Proof ────────────────────────────────────────────

    def prove_input(
        self,
        capability_id: str,
        input_schema: dict[str, Any],
        input_payload: dict[str, Any],
    ) -> ZKInputProof:
        """Generate ZK proof that input satisfies the capability's schema.

        Consumer calls this before invoke. The proof hides the actual input
        but proves it's well-formed.
        """
        schema_hash = hashlib.sha256(
            json.dumps(input_schema, sort_keys=True).encode()
        ).hexdigest()

        # NOTE: SHA-256 hash, NOT a real Pedersen commitment.
        # Not hiding, not binding. Simulated for development only.
        input_json = json.dumps(input_payload, sort_keys=True)
        input_commitment = hashlib.sha256(
            f"simulated_commitment:{input_json}:{int(time.time())}".encode()
        ).hexdigest()

        # Nullifier to prevent double-use
        nullifier = hashlib.sha256(
            f"{capability_id}:{input_commitment}:{time.time()}".encode()
        ).hexdigest()[:32]

        # Simulated Groth16 proof
        # NOTE: This is a SHA-256 hash of public values, NOT a Groth16 proof.
        # Anyone can recompute this — it proves nothing.
        # Production requires circom circuit + bellman/bn254 prover.
        proof_bytes = hashlib.sha256(
            f"simulated_proof:input:{schema_hash}:{input_commitment}:{nullifier}".encode()
        ).hexdigest()

        # Public signals: schema hash, commitment, capability ID
        public_signals = [schema_hash, input_commitment, capability_id]

        proof = ZKInputProof(
            proof_id=f"zk_in_{int(time.time())}",
            capability_id=capability_id,
            schema_hash=schema_hash,
            input_commitment=input_commitment,
            nullifier=nullifier,
            proof_bytes=proof_bytes,
            public_signals=public_signals,
        ).sign(self.signer)

        # NOTE: Nullifier marking happens in verify_input_proof, not here.
        # Adding to set during prove would self-DoS private_invoke_flow
        # (the same ZKProver instance proves AND verifies).
        return proof

    def verify_input_proof(
        self,
        proof: ZKInputProof,
        expected_schema_hash: str,
        expected_capability_id: str,
        prover_public_key: str,
    ) -> dict[str, Any]:
        """Verify a ZK input proof.

        Returns {valid: bool, reason: str}
        """
        # Check signature
        if not self.signer.verify(prover_public_key, proof.signature, proof.canonical()):
            return self._mark_simulated({"valid": False, "reason": "Invalid proof signature"})

        # Check nullifier not already used
        # Nullifier double-spend check (best-effort for simulated proofs)
        if proof.nullifier in self._used_nullifiers:
            return self._mark_simulated({"valid": False, "reason": "Nullifier already used (double-spend attempt)"})

        # Check schema hash matches
        if proof.schema_hash != expected_schema_hash:
            return self._mark_simulated({"valid": False, "reason": "Schema hash mismatch"})

        # Check capability ID
        if proof.capability_id != expected_capability_id:
            return self._mark_simulated({"valid": False, "reason": "Capability ID mismatch"})

        # Simulate ZK proof verification (in production: actual Groth16 verify)
        expected_proof = hashlib.sha256(
            f"simulated_proof:input:{proof.schema_hash}:{proof.input_commitment}:{proof.nullifier}".encode()
        ).hexdigest()

        if proof.proof_bytes != expected_proof:
            return self._mark_simulated({"valid": False, "reason": "ZK proof verification failed"})

        # Mark nullifier as used only on successful verification (prevents replay).
        self._used_nullifiers.add(proof.nullifier)
        return self._mark_simulated({"valid": True, "reason": "Proof verified — input is valid without being revealed"})

    # ── Output Proof ───────────────────────────────────────────

    def prove_output(
        self,
        invocation_id: str,
        capability_id: str,
        input_commitment: str,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any],
    ) -> ZKOutputProof:
        """Generate ZK proof that output is the correct execution result.

        Provider calls this after execution. Proves correctness without
        revealing model weights or the full computation trace.
        """
        output_json = json.dumps(output_payload, sort_keys=True)
        output_commitment = hashlib.sha256(
            f"simulated_output_commitment:{output_json}:{int(time.time())}".encode()
        ).hexdigest()

        # Simulated Groth16 proof — proves execution correctness
        proof_bytes = hashlib.sha256(
            f"groth16:output:{invocation_id}:{input_commitment}:{output_commitment}".encode()
        ).hexdigest()

        public_signals = [invocation_id, input_commitment, output_commitment, capability_id]

        proof = ZKOutputProof(
            proof_id=f"zk_out_{int(time.time())}",
            invocation_id=invocation_id,
            capability_id=capability_id,
            input_commitment=input_commitment,
            output_commitment=output_commitment,
            proof_bytes=proof_bytes,
            public_signals=public_signals,
        ).sign(self.signer)

        return proof

    def verify_output_proof(
        self,
        proof: ZKOutputProof,
        expected_input_commitment: str,
        expected_capability_id: str,
        prover_public_key: str,
    ) -> dict[str, Any]:
        """Verify a ZK output proof."""
        if not self.signer.verify(prover_public_key, proof.signature, proof.canonical()):
            return self._mark_simulated({"valid": False, "reason": "Invalid proof signature"})

        if proof.input_commitment != expected_input_commitment:
            return self._mark_simulated({"valid": False, "reason": "Input commitment mismatch — result is for different input"})

        if proof.capability_id != expected_capability_id:
            return self._mark_simulated({"valid": False, "reason": "Capability ID mismatch"})

        expected_proof = hashlib.sha256(
            f"groth16:output:{proof.invocation_id}:{proof.input_commitment}:{proof.output_commitment}".encode()
        ).hexdigest()

        if proof.proof_bytes != expected_proof:
            return self._mark_simulated({"valid": False, "reason": "ZK proof verification failed"})

        return self._mark_simulated({"valid": True, "reason": "Proof verified — output is correct without revealing execution trace"})

    # ── Combined ZK Flow ───────────────────────────────────────

    def private_invoke_flow(
        self,
        capability_id: str,
        product_id: str,
        input_schema: dict[str, Any],
        input_payload: dict[str, Any],
        executor,  # Callable: (product_id, cap_id, input) → output
    ) -> dict[str, Any]:
        """Full ZK-private invocation cycle.

        1. Consumer: prove input validity (ZK)
        2. Provider: verify input proof
        3. Provider: execute capability
        4. Provider: prove output correctness (ZK)
        5. Consumer: verify output proof

        Neither party sees the other's private data.
        """
        # Step 1: Consumer generates input proof
        schema_hash = hashlib.sha256(
            json.dumps(input_schema, sort_keys=True).encode()
        ).hexdigest()

        input_proof = self.prove_input(capability_id, input_schema, input_payload)

        # Step 2: Provider verifies input proof
        verification = self.verify_input_proof(
            input_proof, schema_hash, capability_id, self.signer.public_key_b64,
        )
        if not verification["valid"]:
            return self._mark_simulated({
                "success": False,
                "error": "ZK input proof rejected",
                "detail": verification,
            })

        # Step 3: Execute
        result = executor(product_id, capability_id, {"zk_input_commitment": input_proof.input_commitment})

        # Step 4: Provider generates output proof
        invocation_id = f"zk_invoke_{int(time.time())}"
        output_proof = self.prove_output(
            invocation_id, capability_id,
            input_proof.input_commitment, input_payload, result,
        )

        # Step 5: Consumer verifies output proof
        output_verification = self.verify_output_proof(
            output_proof, input_proof.input_commitment, capability_id,
            self.signer.public_key_b64,
        )

        return self._mark_simulated({
            "success": output_verification["valid"],
            "invocation_id": invocation_id,
            "input_proof": {
                "proof_id": input_proof.proof_id,
                "schema_hash": input_proof.schema_hash[:16] + "...",
                "input_commitment": input_proof.input_commitment[:16] + "...",
                "verified": verification["valid"],
            },
            "output_proof": {
                "proof_id": output_proof.proof_id,
                "output_commitment": output_proof.output_commitment[:16] + "...",
                "verified": output_verification["valid"],
            },
            "result": result,
            # privacy_guarantees deliberately understates — this is a simulation,
            # not a real ZK proof. Setting hidden=False to prevent any caller
            # treating these properties as cryptographically enforced.
            "privacy_guarantees": {
                "input_hidden": False,
                "execution_trace_hidden": False,
                "double_spend_protected": False,
                "zk_scheme": "SHA-256 commitment (simulated only)",
                "note": "Real ZK requires circom circuits + bn254 curve. This output is for development/testing only.",
            },
        })

    def stats(self) -> dict[str, Any]:
        return self._mark_simulated({
            "nullifiers_used": len(self._used_nullifiers),
            "zk_scheme": "SHA-256 commitment (simulated only)",
            "production_recommendation": "circom circuits compiled to bn254 via bellman/gnark",
        })


# Backward-compat alias — code that imported ZKProver still works.
# The opt-in env check fires on instantiation, so prod deploys still get the warning.
ZKProver = ZKProverSimulated
