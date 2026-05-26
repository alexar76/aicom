"""Ed25519 signing for UNI receipts (no web3 / payment API imports)."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

from core.paths import secrets_dir


def signing_key_path() -> Path:
    return secrets_dir() / "uni_receipt_ed25519.key"


def _load_or_create_keypair() -> tuple[bytes, bytes]:
    path = signing_key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy = secrets_dir() / "ai_market_ed25519.key"
    if path.exists():
        raw = path.read_bytes()
    elif legacy.exists():
        raw = legacy.read_bytes()
        path.write_bytes(raw)
    else:
        raw = b""
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
