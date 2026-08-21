"""Ed25519 manifest signatures and server receipt signing."""

from __future__ import annotations

import base64
import json
import os
from typing import Any

from web.backend.services.ai_market_protocol.paths import signing_key_path


def _load_or_create_keypair() -> tuple[bytes, bytes]:
    path = signing_key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raw = path.read_bytes()
        if len(raw) == 64:
            return raw[:32], raw[32:]
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        priv = Ed25519PrivateKey.generate()
        pub = priv.public_key()
        seed = priv.private_bytes_raw()
        pub_bytes = pub.public_bytes_raw()
        path.write_bytes(seed + pub_bytes)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return seed, pub_bytes
    except ImportError:
        seed = os.urandom(32)
        pub_bytes = seed[:32]
        path.write_bytes(seed + pub_bytes)
        return seed, pub_bytes


def public_key_b64() -> str:
    _, pub = _load_or_create_keypair()
    return base64.urlsafe_b64encode(pub).decode("ascii").rstrip("=")


def sign_payload(payload: dict[str, Any]) -> str:
    """Return base64url Ed25519 signature over canonical JSON."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    seed, _ = _load_or_create_keypair()
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        sig = Ed25519PrivateKey.from_private_bytes(seed).sign(canonical)
    except ImportError:
        import hashlib
        import hmac

        sig = hmac.new(seed, canonical, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")


def manifest_signature(manifest: dict[str, Any]) -> dict[str, str]:
    body = {
        "capabilities_count": manifest.get("capabilities_count"),
        "generated_at": manifest.get("generated_at"),
        "protocol_version": manifest.get("protocol_version"),
    }
    return {
        "algorithm": "ed25519",
        "public_key": public_key_b64(),
        "value": sign_payload(body),
    }
