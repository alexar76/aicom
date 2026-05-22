"""Ed25519 signing for hub manifests and receipts."""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any


def _ensure_keypair(path: Path) -> tuple[bytes, bytes]:
    """Load or create an Ed25519 keypair."""
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
        raise ImportError(
            "cryptography>=44 is required for Ed25519 signing. "
            "Install it: pip install cryptography>=44"
        )


class Signer:
    """Ed25519 signer for a hub instance."""

    def __init__(self, key_path: str | Path = "data/hub_signing_key"):
        self.key_path = Path(key_path)
        self._seed, self._pub_bytes = _ensure_keypair(self.key_path)
        self._public_key_b64 = base64.b64encode(self._pub_bytes).decode()

    @property
    def public_key_b64(self) -> str:
        return self._public_key_b64

    def sign(self, payload: bytes) -> bytes:
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

            return Ed25519PrivateKey.from_private_bytes(self._seed).sign(payload)
        except ImportError:
            raise ImportError(
                "cryptography>=44 is required for Ed25519 signing. "
                "Install it: pip install cryptography>=44"
            )

    def sign_canonical(self, canonical: str) -> str:
        sig = self.sign(canonical.encode())
        return base64.b64encode(sig).decode()

    def verify(self, public_key_b64: str, signature_b64: str, canonical: str) -> bool:
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            from cryptography.exceptions import InvalidSignature
        except ImportError:
            raise ImportError(
                "cryptography>=44 is required for Ed25519 verification. "
                "Install it: pip install cryptography>=44"
            )

        try:
            pk_bytes = base64.b64decode(public_key_b64)
            sig_bytes = base64.b64decode(signature_b64)
            Ed25519PublicKey.from_public_bytes(pk_bytes).verify(sig_bytes, canonical.encode())
            return True
        except InvalidSignature:
            return False

    def sign_manifest(self, manifest: dict[str, Any]) -> dict[str, str]:
        canonical = (
            f"capabilities_count:{manifest.get('capabilities_count', 0)}"
            f"|generated_at:{manifest.get('generated_at', '')}"
            f"|protocol_version:{manifest.get('protocol_version', 'v1')}"
        )
        return {
            "algorithm": "ed25519",
            "public_key": self.public_key_b64,
            "value": self.sign_canonical(canonical),
        }

    def sign_receipt(self, receipt: dict[str, Any]) -> dict[str, str]:
        canonical = (
            f"nonce:{receipt.get('nonce','')}"
            f"|product_id:{receipt.get('product_id','')}"
            f"|capability_id:{receipt.get('capability_id','')}"
            f"|price_usd:{receipt.get('price_usd',0)}"
            f"|timestamp:{receipt.get('timestamp','')}"
        )
        return {
            "algorithm": "ed25519",
            "value": self.sign_canonical(canonical),
        }

    def verify_manifest_signature(self, manifest: dict[str, Any]) -> bool:
        sig = manifest.get("signature") or {}
        if not sig:
            return False
        canonical = (
            f"capabilities_count:{manifest.get('capabilities_count', 0)}"
            f"|generated_at:{manifest.get('generated_at', '')}"
            f"|protocol_version:{manifest.get('protocol_version', 'v1')}"
        )
        return self.verify(sig.get("public_key", ""), sig.get("value", ""), canonical)
