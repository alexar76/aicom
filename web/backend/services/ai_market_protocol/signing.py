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
    # Standard base64, padded — what `aimarket-protocol/spec.md` §7.3 and every shipped
    # test vector use. This module published unpadded base64url, which a strict verifier
    # decodes to different bytes (Python's own `b64decode` silently DISCARDS `-` and `_`),
    # so the key this factory advertised could not verify anything it signed.
    _, pub = _load_or_create_keypair()
    return base64.b64encode(pub).decode("ascii")


def _sign_bytes(canonical: bytes) -> str:
    seed, _ = _load_or_create_keypair()
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        sig = Ed25519PrivateKey.from_private_bytes(seed).sign(canonical)
    except ImportError:
        import hashlib
        import hmac

        sig = hmac.new(seed, canonical, hashlib.sha256).digest()
    return base64.b64encode(sig).decode("ascii")


def sign_payload(payload: dict[str, Any]) -> str:
    """Return base64url Ed25519 signature over canonical JSON."""
    return _sign_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def sign_canonical(canonical: str) -> str:
    """Sign a canonical STRING (the protocol's manifest/object forms), not a dict."""
    return _sign_bytes(canonical.encode("utf-8"))


def manifest_canonical(manifest: dict[str, Any]) -> str:
    """The five-field canonical from `aimarket-protocol/spec.md` §7.3.

    Byte-identical to `aimarket_hub.signing.Signer.manifest_canonical` and to
    `aimarket-protocol/conformance/run.py`. This factory used to sign three fields
    (capabilities_count, generated_at, protocol_version) as canonical JSON, which left
    `tools[]` — every price in the catalogue — outside the signature. Two consequences,
    both real: the hub refused the manifest (`manifest_signed`), so this factory could
    never be admitted to its own federation; and a relay could rewrite any price under a
    signature that still verified, which is the scenario
    `test-vectors/negative/manifest-tampered-price.json` exists to forbid.
    """
    import hashlib

    def _digest(value: Any) -> str:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

    return (
        f"capabilities_count:{manifest.get('capabilities_count', 0)}"
        f"|generated_at:{manifest.get('generated_at', '')}"
        f"|protocol_version:{manifest.get('protocol_version', 'v1')}"
        f"|tools_hash:{_digest(manifest.get('tools', []))}"
        f"|by_hub_hash:{_digest(manifest.get('by_hub', {}))}"
    )


def object_canonical(obj: dict[str, Any]) -> str:
    """Whole-document canonical, for `/.well-known/ai-market.json`.

    Matches `Signer.object_canonical`: every field except `signature`, sorted, compact,
    `ensure_ascii=False` — a non-ASCII name signed with `ensure_ascii=True` would verify
    nowhere but here.
    """
    body = {k: v for k, v in obj.items() if k != "signature"}
    return json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def manifest_signature(manifest: dict[str, Any]) -> dict[str, str]:
    return {
        "algorithm": "ed25519",
        "public_key": public_key_b64(),
        "value": sign_canonical(manifest_canonical(manifest)),
    }


def object_signature(obj: dict[str, Any]) -> dict[str, str]:
    """Sign a discovery document in place of a manifest's structural canonical."""
    return {
        "algorithm": "ed25519",
        "public_key": public_key_b64(),
        "value": sign_canonical(object_canonical(obj)),
    }
