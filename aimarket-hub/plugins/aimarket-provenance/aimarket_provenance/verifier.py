"""Standalone verification logic for ProvenanceReceipts.

No FastAPI or database dependencies — this module can be used by the API,
CLI tools, and serves as specification reference for the JS verifier.
"""

from __future__ import annotations

import re
import time
from calendar import timegm
from dataclasses import dataclass, field
from typing import Any

from aimarket_hub.signing import Signer

from .receipt import ProvenanceReceipt


@dataclass
class VerificationResult:
    """Result of a complete provenance receipt verification."""

    valid: bool = False
    checks: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "checks": self.checks,
            "errors": self.errors,
        }


def verify_receipt(
    receipt: ProvenanceReceipt, signer: Signer
) -> VerificationResult:
    """Verify a provenance receipt end-to-end.

    Checks performed:
    1. Structural validity (all required fields)
    2. Ed25519 signature against embedded public key
    3. Timestamp not in the future (> 5 min clock skew)
    4. Input/output hashes are 64-char hex SHA-256
    5. Parent receipts have valid ID format
    6. TEE attestation not expired (if present)
    """
    result = VerificationResult()
    required = [
        "model_id", "provider_hub", "input_hash",
        "output_hash", "timestamp",
    ]

    # 1. Structural
    for field_name in required:
        if not getattr(receipt, field_name, ""):
            result.errors.append(f"Missing required field: {field_name}")

    if result.errors:
        result.valid = False
        return result
    result.checks.append({"check": "structure", "passed": True})

    # 2. Signature — self-contained via embedded public key
    if not receipt.proof_value:
        result.errors.append("Missing proof value (signature)")
    else:
        sig_valid = receipt.verify(signer)
        result.checks.append({
            "check": "signature",
            "passed": sig_valid,
            "algorithm": "Ed25519",
            "public_key": receipt.issuer_public_key_b64,
        })
        if not sig_valid:
            result.errors.append("Ed25519 signature verification failed")

    # 3. Timestamp (future skew + max age check)
    MAX_RECEIPT_AGE_SECS = 90 * 86400  # 90 days
    try:
        ts = timegm(time.strptime(receipt.timestamp, "%Y-%m-%dT%H:%M:%SZ"))
        now = time.time()
        ts_valid = True
        if ts > now + 300:
            result.errors.append("Timestamp is in the future (clock skew > 5 min)")
            ts_valid = False
        if ts < now - MAX_RECEIPT_AGE_SECS:
            result.errors.append(
                f"Timestamp is too old (>{MAX_RECEIPT_AGE_SECS // 86400} days)"
            )
            ts_valid = False
        result.checks.append({
            "check": "timestamp",
            "passed": ts_valid,
            "value": receipt.timestamp,
        })
    except (ValueError, OSError):
        result.errors.append(f"Invalid timestamp format: {receipt.timestamp}")

    # 4. Hash format
    hash_ok = True
    if not re.match(r"^[a-f0-9]{64}$", receipt.input_hash):
        result.errors.append(f"Invalid input_hash format: {receipt.input_hash}")
        hash_ok = False
    if not re.match(r"^[a-f0-9]{64}$", receipt.output_hash):
        result.errors.append(f"Invalid output_hash format: {receipt.output_hash}")
        hash_ok = False
    result.checks.append({"check": "hash_format", "passed": hash_ok})

    # 5. Parent receipts format
    if receipt.parent_receipts:
        bad = [
            pid for pid in receipt.parent_receipts
            if not (pid.startswith("urn:uuid:") or pid.startswith("https://"))
        ]
        if bad:
            result.errors.append(
                f"Invalid parent_receipt format: {', '.join(bad[:3])}"
            )
        result.checks.append({
            "check": "parent_receipts",
            "passed": len(bad) == 0,
            "count": len(receipt.parent_receipts),
        })

    # 6. TEE attestation (verify signature + expiry)
    if receipt.tee_attestation:
        try:
            from aimarket_hub.tee_attestation import TEEAttestation

            att_data = receipt.tee_attestation
            att = TEEAttestation(
                platform=att_data.get("platform", ""),
                enclave_id=att_data.get("enclaveId", ""),
                code_hash=att_data.get("codeHash", ""),
                pcr_values=att_data.get("pcrValues", {}),
                instance_id=att_data.get("instanceId", ""),
                region=att_data.get("region", ""),
                timestamp=att_data.get("timestamp", ""),
                ttl_s=att_data.get("ttlS", 300),
                signature=att_data.get("signature", ""),
            )
            # Verify TEE signature (not just expiry)
            expected_code_hash = att_data.get("codeHash", "")
            if expected_code_hash and att.signature:
                tee_ok = att.verify(
                    expected_code_hash=expected_code_hash,
                    signer=signer,
                    enclave_public_key=signer.public_key_b64,
                )
            else:
                tee_ok = not att.is_expired()

            result.checks.append({
                "check": "tee_attestation",
                "passed": tee_ok,
                "platform": att.platform,
                "code_hash_verified": bool(expected_code_hash and att.signature),
            })
            if not tee_ok:
                result.errors.append(
                    "TEE attestation verification failed (signature or expiry)"
                )
        except Exception as exc:
            result.errors.append(f"TEE attestation error: {exc}")

    result.valid = len(result.errors) == 0
    return result
