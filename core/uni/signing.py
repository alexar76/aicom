"""Ed25519 signing for UNI receipts (no web3 / payment API imports)."""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING, Any

from core.ed25519_keys import load_or_create_ed25519_keypair
from core.paths import secrets_dir

if TYPE_CHECKING:
    from pathlib import Path


def signing_key_path() -> Path:
    return secrets_dir() / "uni_receipt_ed25519.key"


def _load_or_create_keypair() -> tuple[bytes, bytes]:
    return load_or_create_ed25519_keypair(
        signing_key_path(), legacy_path=secrets_dir() / "ai_market_ed25519.key",
    )


def public_key_b64() -> str:
    _, pub = _load_or_create_keypair()
    return base64.urlsafe_b64encode(pub).decode("ascii").rstrip("=")


def sign_payload(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    seed, _ = _load_or_create_keypair()
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    sig = Ed25519PrivateKey.from_private_bytes(seed).sign(canonical)
    return base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")
