"""ProvenanceReceipt — self-contained cryptographic receipt for AI outputs.

Design:
- JSON-LD compatible with W3C Verifiable Credentials
- All verification material embedded (public keys in JWK, hashes)
- No external context needed for verification
- Reuses aimarket_hub.signing.Signer for Ed25519 operations
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import Any

from aimarket_hub.signing import Signer

# ── Constants ──────────────────────────────────────────────────────

PROVENANCE_PROOF_TYPE = "Ed25519Signature2018"
PROVENANCE_CONTEXT = [
    "https://www.w3.org/2018/credentials/v1",
    "https://verify.aimarket.org/schemas/provenance-receipt.json",
]
HASH_ALGORITHM = "SHA-256"


# ── Hash helper ────────────────────────────────────────────────────

def json_canonical(obj: Any) -> str:
    """RFC 8785 JSON Canonicalization Scheme (JCS).

    Produces a deterministic serialization regardless of key ordering,
    whitespace, or Unicode normalization. Used for hash preimages and
    canonical signing forms.
    """
    if isinstance(obj, dict):
        inner = ",".join(
            f"{json_canonical(k)}:{json_canonical(v)}"
            for k, v in sorted(obj.items(), key=lambda x: x[0])
        )
        return "{" + inner + "}"
    if isinstance(obj, (list, tuple)):
        inner = ",".join(json_canonical(i) for i in obj)
        return "[" + inner + "]"
    if isinstance(obj, str):
        # Unicode NFC normalization + escape for JSON string
        normalized = unicodedata.normalize("NFC", obj)
        return json.dumps(normalized, ensure_ascii=False)
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if obj is None:
        return "null"
    if isinstance(obj, (int, float)):
        if isinstance(obj, float):
            if obj == int(obj):
                return f"{int(obj)}.0"
            return f"{obj:.10f}".rstrip("0").rstrip(".")
        return str(obj)
    return json.dumps(obj, ensure_ascii=False)


def compute_hash(data: dict[str, Any]) -> str:
    """SHA-256 hash of RFC 8785 canonical JSON representation.

    Uses NFC Unicode normalization for cross-platform consistency (Python/JS).
    """
    canonical = json_canonical(data)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── Canonical form for signing ─────────────────────────────────────

def credential_subject_canonical(subject: dict[str, Any]) -> str:
    """Pipe-delimited canonical form of credentialSubject fields.

    Uses RFC 8785 JCS for nested objects to ensure deterministic
    serialization across Python and JavaScript implementations.

    Format: key:value|key:value|...
    Fields are sorted alphabetically.
    """
    parts: list[str] = []
    for key in sorted(subject.keys()):
        val = subject[key]
        if isinstance(val, dict):
            val = json_canonical(val)
        elif isinstance(val, list):
            val = json_canonical(val)
        elif isinstance(val, float):
            if val == int(val):
                val = f"{int(val)}.0"
            else:
                val = f"{val:.10f}".rstrip("0").rstrip(".")
        parts.append(f"{key}:{val}")
    return "|".join(parts)


# ── JWK ↔ base64 helpers ───────────────────────────────────────────

def public_key_to_jwk(public_key_b64: str) -> dict[str, str]:
    """Convert base64-encoded Ed25519 public key to JWK (RFC 8037)."""
    raw = base64.b64decode(public_key_b64)
    x = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    return {"kty": "OKP", "crv": "Ed25519", "x": x}


def public_key_from_jwk(jwk: dict[str, str]) -> str:
    """Convert JWK back to base64-encoded Ed25519 public key."""
    x = jwk.get("x", "")
    padding = 4 - len(x) % 4
    if padding != 4:
        x += "=" * padding
    raw = base64.urlsafe_b64decode(x)
    return base64.b64encode(raw).decode()


# ── ProvenanceReceipt ──────────────────────────────────────────────

@dataclass
class ProvenanceReceipt:
    """Self-contained cryptographic receipt for an AI-generated output.

    Embedds the issuer's Ed25519 public key as JWK — verification
    requires no external lookups. JSON-LD compatible with W3C VC.

    Canonical form for signing is a pipe-delimited string of
    credentialSubject fields (matching the existing sign_canonical pattern).
    """

    # W3C VC fields
    context: list[str] = field(default_factory=lambda: list(PROVENANCE_CONTEXT))
    receipt_id: str = ""
    type: list[str] = field(default_factory=lambda: ["VerifiableCredential", "AIProvenanceReceipt"])

    # Issuer
    issuer_id: str = ""
    issuer_name: str = ""
    issuer_public_key_b64: str = ""

    # Credential subject
    model_id: str = ""
    provider_hub: str = ""
    input_hash: str = ""   # 64-char hex SHA-256
    output_hash: str = ""  # 64-char hex SHA-256
    parent_receipts: list[str] = field(default_factory=list)
    timestamp: str = ""    # ISO 8601
    latency_ms: int = 0
    price_usd: float = 0.0
    invocation_nonce: str = ""

    # Optional attestations
    tee_attestation: dict[str, Any] | None = None
    zk_input_proof: dict[str, Any] | None = None
    zk_output_proof: dict[str, Any] | None = None
    reputation_score: float | None = None

    # Proof
    proof_type: str = PROVENANCE_PROOF_TYPE
    proof_created: str = ""
    proof_verification_method: str = ""
    proof_value: str = ""  # base64-encoded Ed25519 signature

    # Hub info
    hub_name: str = ""
    hub_version: str = ""
    protocol_version: str = "v2"

    # ── Factory ─────────────────────────────────────────────────

    @classmethod
    def create(
        cls,
        *,
        model_id: str,
        provider_hub: str,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any],
        signer: Signer,
        hub_name: str = "",
        hub_version: str = "",
        parent_receipts: list[str] | None = None,
        tee_attestation: dict[str, Any] | None = None,
        latency_ms: int = 0,
        price_usd: float = 0.0,
        invocation_nonce: str | None = None,
        reputation_score: float | None = None,
    ) -> "ProvenanceReceipt":
        """Create and sign a new ProvenanceReceipt from invocation data."""
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        nonce = invocation_nonce or str(uuid.uuid4())

        receipt = cls(
            receipt_id=f"urn:uuid:{uuid.uuid4()}",
            issuer_id=provider_hub,
            issuer_name=hub_name or provider_hub,
            issuer_public_key_b64=signer.public_key_b64,
            model_id=model_id,
            provider_hub=provider_hub,
            input_hash=compute_hash(input_payload),
            output_hash=compute_hash(output_payload),
            parent_receipts=parent_receipts or [],
            timestamp=now,
            latency_ms=latency_ms,
            price_usd=price_usd,
            invocation_nonce=nonce,
            tee_attestation=tee_attestation,
            reputation_score=reputation_score,
            proof_created=now,
            proof_verification_method=f"did:key:{signer.public_key_b64[:32]}",
            hub_name=hub_name or provider_hub,
            hub_version=hub_version,
        )
        receipt.sign(signer)
        return receipt

    # ── Credential subject ─────────────────────────────────────

    def _build_credential_subject(self) -> dict[str, Any]:
        subject: dict[str, Any] = {
            "modelId": self.model_id,
            "providerHub": self.provider_hub,
            "inputHash": {"algorithm": HASH_ALGORITHM, "value": self.input_hash},
            "outputHash": {"algorithm": HASH_ALGORITHM, "value": self.output_hash},
            "parentReceipts": list(self.parent_receipts),
            "timestamp": self.timestamp,
        }
        if self.latency_ms > 0:
            subject["latencyMs"] = self.latency_ms
        if self.price_usd > 0:
            subject["priceUsd"] = self.price_usd
        if self.invocation_nonce:
            subject["invocationNonce"] = self.invocation_nonce
        if self.tee_attestation:
            subject["teeAttestation"] = self.tee_attestation
        if self.zk_input_proof:
            subject["zkInputProof"] = self.zk_input_proof
        if self.zk_output_proof:
            subject["zkOutputProof"] = self.zk_output_proof
        if self.reputation_score is not None:
            subject["reputationScore"] = self.reputation_score
        return subject

    # ── Signing / Verification ─────────────────────────────────

    def sign(self, signer: Signer) -> None:
        """Sign the credential subject with the hub's Ed25519 key."""
        subject = self._build_credential_subject()
        canonical = credential_subject_canonical(subject)
        self.proof_value = signer.sign_canonical(canonical)
        self.proof_created = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
        )
        self.issuer_public_key_b64 = signer.public_key_b64

    def verify(self, signer: Signer) -> bool:
        """Verify the receipt's Ed25519 signature.

        Uses the embedded issuer_public_key_b64 — no external key lookup needed.
        Returns False on any verification error (bad signature, invalid base64, etc.).
        """
        if not self.proof_value or not self.issuer_public_key_b64:
            return False
        try:
            subject = self._build_credential_subject()
            canonical = credential_subject_canonical(subject)
            return signer.verify(
                self.issuer_public_key_b64,
                self.proof_value,
                canonical,
            )
        except Exception:
            return False

    # ── Serialization ──────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Serialize to W3C VC-compatible dict."""
        jwk = public_key_to_jwk(self.issuer_public_key_b64)
        issuance = self.proof_created or self.timestamp

        return {
            "@context": list(self.context),
            "id": self.receipt_id,
            "type": list(self.type),
            "issuer": {
                "id": self.issuer_id,
                "name": self.issuer_name,
                "publicKeyJwk": jwk,
            },
            "issuanceDate": issuance,
            "credentialSubject": self._build_credential_subject(),
            "proof": {
                "type": self.proof_type,
                "created": self.proof_created or self.timestamp,
                "verificationMethod": self.proof_verification_method,
                "proofPurpose": "assertionMethod",
                "proofValue": self.proof_value,
            },
            "hubInfo": {
                "hubName": self.hub_name,
                "hubVersion": self.hub_version,
                "protocolVersion": self.protocol_version,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProvenanceReceipt":
        """Deserialize from a W3C VC-compatible dict with input validation."""
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data).__name__}")

        issuer = data.get("issuer", {})
        subject = data.get("credentialSubject", {})
        proof = data.get("proof", {})
        hub_info = data.get("hubInfo", {})

        ih = subject.get("inputHash", {})
        oh = subject.get("outputHash", {})

        jwk = issuer.get("publicKeyJwk", {})
        pubkey = public_key_from_jwk(jwk) if jwk else ""

        def _safe_int(val: Any, default: int = 0) -> int:
            try:
                return int(val)
            except (TypeError, ValueError):
                return default

        def _safe_float(val: Any, default: float = 0.0) -> float:
            try:
                return float(val)
            except (TypeError, ValueError):
                return default

        def _safe_str(val: Any, default: str = "") -> str:
            return str(val) if val is not None else default

        def _safe_list(val: Any) -> list[str]:
            if isinstance(val, list):
                return [str(v) for v in val]
            return []

        return cls(
            context=_safe_list(data.get("@context")) or list(PROVENANCE_CONTEXT),
            receipt_id=_safe_str(data.get("id")),
            type=_safe_list(data.get("type")) or ["VerifiableCredential"],
            issuer_id=_safe_str(issuer.get("id")),
            issuer_name=_safe_str(issuer.get("name")),
            issuer_public_key_b64=pubkey,
            model_id=_safe_str(subject.get("modelId")),
            provider_hub=_safe_str(subject.get("providerHub")),
            input_hash=_safe_str(ih.get("value") if isinstance(ih, dict) else None),
            output_hash=_safe_str(oh.get("value") if isinstance(oh, dict) else None),
            parent_receipts=_safe_list(subject.get("parentReceipts")),
            timestamp=_safe_str(subject.get("timestamp")),
            latency_ms=_safe_int(subject.get("latencyMs")),
            price_usd=_safe_float(subject.get("priceUsd")),
            invocation_nonce=_safe_str(subject.get("invocationNonce")),
            tee_attestation=subject.get("teeAttestation") if isinstance(subject.get("teeAttestation"), dict) else None,
            zk_input_proof=subject.get("zkInputProof") if isinstance(subject.get("zkInputProof"), dict) else None,
            zk_output_proof=subject.get("zkOutputProof") if isinstance(subject.get("zkOutputProof"), dict) else None,
            reputation_score=_safe_float(subject.get("reputationScore")) if subject.get("reputationScore") is not None else None,
            proof_type=_safe_str(proof.get("type"), PROVENANCE_PROOF_TYPE),
            proof_created=_safe_str(proof.get("created")),
            proof_verification_method=_safe_str(proof.get("verificationMethod")),
            proof_value=_safe_str(proof.get("proofValue")),
            hub_name=_safe_str(hub_info.get("hubName")),
            hub_version=_safe_str(hub_info.get("hubVersion")),
            protocol_version=_safe_str(hub_info.get("protocolVersion"), "v2"),
        )
