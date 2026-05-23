"""Zero-trust agent verification — cryptographic and policy checks."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa

from ai_service_mesh.security import url_is_safe


@dataclass
class VerificationResult:
    ok: bool
    trust_score: float
    reasons: list[str]


def _load_public_key(pem: str):
    try:
        key = serialization.load_pem_public_key(pem.encode("utf-8"))
    except Exception:
        return None
    if not isinstance(key, (rsa.RSAPublicKey, ed25519.Ed25519PublicKey)):
        return None
    return key


def verify_agent_registration(
    *,
    name: str,
    endpoint_url: str,
    public_key_pem: str,
    capabilities: list[str],
    attestation: str,
    allow_localhost: bool = False,
) -> VerificationResult:
    reasons: list[str] = []
    score = 0.0

    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9 _\-\.]{1,118}[a-zA-Z0-9]$", name.strip()):
        reasons.append("invalid_name")
    else:
        score += 0.15

    if not url_is_safe(endpoint_url, allow_localhost=allow_localhost):
        reasons.append("unsafe_endpoint")
    else:
        score += 0.25

    key = _load_public_key(public_key_pem)
    if not key:
        reasons.append("invalid_public_key")
    else:
        score += 0.25

    if not capabilities or len(capabilities) > 32:
        reasons.append("invalid_capabilities")
    else:
        score += 0.15

    if attestation:
        expected = hashlib.sha256(
            f"{name}|{endpoint_url}|{','.join(sorted(capabilities))}".encode()
        ).digest()
        try:
            pad = "=" * (-len(attestation) % 4)
            got = base64.urlsafe_b64decode(attestation + pad)
            if len(got) == 32 and hmac.compare_digest(got, expected):
                score += 0.2
            else:
                reasons.append("weak_attestation")
        except Exception:
            reasons.append("invalid_attestation")
    else:
        reasons.append("missing_attestation")

    ok = "unsafe_endpoint" not in reasons and "invalid_public_key" not in reasons
    return VerificationResult(ok=ok, trust_score=min(1.0, score), reasons=reasons)
