"""Ed25519 signing for hub manifests and receipts.

Fail-fast: refuses to initialize if cryptography is not installed
or if an existing key file is corrupted.
"""

from __future__ import annotations

import base64
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _ensure_keypair(path: Path) -> tuple[bytes, bytes]:
    """Load or create an Ed25519 keypair.

    Raises:
        ImportError: cryptography not installed.
        RuntimeError: existing key file corrupted (fail-fast, no silent regen).
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # Verify cryptography is available BEFORE touching any files
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: F401
    except ImportError:
        raise ImportError(
            "cryptography>=44 is required for Ed25519 signing. "
            "Install it: pip install cryptography>=44"
        )

    if path.exists():
        raw = path.read_bytes()
        if len(raw) == 64:
            return raw[:32], raw[32:]
        # Corrupted key file — fail fast, don't silently regenerate
        raise RuntimeError(
            f"Ed25519 key file {path} exists but is corrupted "
            f"(size={len(raw)}, expected 64 bytes). "
            "Remove it manually if you want to regenerate, "
            "or restore from backup."
        )

    # No key file — generate a new one
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

    is_prod = os.environ.get("AIFACTORY_PROD", "").strip() == "1"
    if is_prod:
        logger.warning(
            "PRODUCTION: New Ed25519 keypair generated at %s. "
            "This key signs all hub manifests and receipts. "
            "Back it up immediately — if lost, federation trust is broken.",
            path,
        )

    return seed, pub_bytes


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
        # Sign over structural integrity fields + content digest.
        # The manifest signature now covers the full tools[] array via a hash
        # so that any price/trust/agent modification invalidates the signature.
        import hashlib, json
        tools = manifest.get("tools", [])
        tools_hash = hashlib.sha256(
            json.dumps(tools, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        canonical = (
            f"capabilities_count:{manifest.get('capabilities_count', 0)}"
            f"|generated_at:{manifest.get('generated_at', '')}"
            f"|protocol_version:{manifest.get('protocol_version', 'v1')}"
            f"|tools_hash:{tools_hash}"
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
            f"|success:{1 if receipt.get('success') else 0}"
            f"|latency_ms:{receipt.get('latency_ms',0)}"
        )
        return {
            "algorithm": "ed25519",
            "value": self.sign_canonical(canonical),
        }

    def verify_manifest_signature(
        self, manifest: dict[str, Any], known_public_key: str = ""
    ) -> bool:
        """Verify manifest signature against a KNOWN public key (pinned).

        Args:
            manifest: The manifest dict containing a 'signature' block.
            known_public_key: Peer's public key from a trusted source (DB pinning).
                              MUST be non-empty — empty key returns False.

        Security: The public key MUST come from a trusted source (peer DB record),
        NOT from the signature block itself — otherwise signatures are self-verifying.
        First-contact callers should reject the peer until an operator approves it.
        """
        if not known_public_key:
            # Fail-closed: no pinned key = cannot verify trust chain.
            # Previously fell back to sig.public_key which is self-verifying.
            return False
        sig = manifest.get("signature") or {}
        if not sig:
            return False
        import hashlib, json
        tools = manifest.get("tools", [])
        tools_hash = hashlib.sha256(
            json.dumps(tools, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        canonical = (
            f"capabilities_count:{manifest.get('capabilities_count', 0)}"
            f"|generated_at:{manifest.get('generated_at', '')}"
            f"|protocol_version:{manifest.get('protocol_version', 'v1')}"
            f"|tools_hash:{tools_hash}"
        )
        return self.verify(known_public_key, sig.get("value", ""), canonical)


def verify_crypto_ready(key_path: str | Path = "data/hub_signing_key") -> Signer:
    """Fail-fast crypto initialization for hub startup.

    Returns a Signer or exits the process.
    Call this at the top of main() / create_app().
    """
    try:
        return Signer(key_path=key_path)
    except ImportError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except RuntimeError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
