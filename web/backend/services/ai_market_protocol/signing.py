"""Hybrid (Ed25519 + ML-DSA-65) manifest signatures and server receipt signing."""

from __future__ import annotations

import base64
import contextlib
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from core.ed25519_keys import load_or_create_ed25519_keypair
from web.backend.services.ai_market_protocol.paths import signing_key_path


def _load_or_create_keypair() -> tuple[bytes, bytes]:
    return load_or_create_ed25519_keypair(signing_key_path())


try:  # pragma: no cover - presence is what is under test, not the import line
    from dilithium_py.ml_dsa import ML_DSA_65 as _MLDSA

    _PQ_LIB = True
except ImportError:  # pragma: no cover
    _MLDSA = None
    _PQ_LIB = False


class PQCMisconfigured(RuntimeError):
    """PQ signing is switched on but this process cannot produce an ML-DSA signature."""


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def _read_pq_identity(path: Path) -> tuple[bytes, bytes]:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("PQ signing identity must be a regular file")
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "r", closefd=False) as handle:
            lines = handle.read(20000).splitlines()
        if len(lines) != 2:
            raise ValueError("Invalid PQ signing identity; explicit recovery is required")
        public, private = map(bytes.fromhex, lines)
        if _MLDSA.pk_from_sk(private) != public:
            raise ValueError("PQ signing identity public/private key mismatch")
        return public, private
    finally:
        os.close(fd)


def _atomic_pq_identity(path: Path) -> tuple[bytes, bytes]:
    try:
        return _read_pq_identity(path)
    except FileNotFoundError:
        pass
    public, private = _MLDSA.keygen()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(f"{public.hex()}\n{private.hex()}\n")
            handle.flush()
            os.fsync(handle.fileno())
        with contextlib.suppress(FileExistsError):
            os.link(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return _read_pq_identity(path)
    finally:
        os.unlink(temporary)


def _pq_keypair() -> tuple[bytes, bytes] | None:
    """This node's ML-DSA-65 keypair, or None when hybrid signing is off.

    Kept beside the classical key as ``<key>_mldsa``, the convention every other signer in
    the ecosystem follows, so it persists on whatever volume the Ed25519 key does — a PQ
    key regenerated on each boot would re-key the factory's identity every restart.

    Missing library with the flag ON raises instead of degrading. The quiet fallback is
    what this function exists to prevent: this factory published a classical-only manifest
    all through phase 2 of the PQC migration and nothing said so, until a peer that had
    reached phase 3 (AIMARKET_PQC_REQUIRE=1) began refusing every manifest from here and
    froze its copy of this catalogue for a week while still reporting the peer as healthy.
    """
    if not _truthy(os.environ.get("AIMARKET_PQC")):
        return None
    if not _PQ_LIB:
        raise PQCMisconfigured(
            "AIMARKET_PQC is on but dilithium-py is missing — install it on this signer"
        )
    classical = signing_key_path()
    path = classical.with_name(classical.name + "_mldsa")
    return _atomic_pq_identity(path)


def _pq_fields(canonical: str) -> dict[str, str]:
    """The additive ``pq_*`` block for a signature object; ``{}`` when PQ signing is off.

    The FIELD NAMES are the interoperability contract — a second spelling of ``pq_value``
    is a signature no verifier in the ecosystem looks at.
    """
    pair = _pq_keypair()
    if pair is None:
        return {}
    pk, sk = pair
    return {
        "pq_algorithm": "ml-dsa-65",
        "pq_public_key": base64.b64encode(pk).decode("ascii"),
        "pq_value": base64.b64encode(_MLDSA.sign(sk, canonical.encode("utf-8"))).decode("ascii"),
    }


def public_key_b64() -> str:
    # Standard base64, padded — what `aimarket-protocol/spec.md` §7.3 and every shipped
    # test vector use. This module published unpadded base64url, which a strict verifier
    # decodes to different bytes (Python's own `b64decode` silently DISCARDS `-` and `_`),
    # so the key this factory advertised could not verify anything it signed.
    _, pub = _load_or_create_keypair()
    return base64.b64encode(pub).decode("ascii")


def _sign_bytes(canonical: bytes) -> str:
    seed, _ = _load_or_create_keypair()
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    sig = Ed25519PrivateKey.from_private_bytes(seed).sign(canonical)
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
    canonical = manifest_canonical(manifest)
    return {
        "algorithm": "ed25519",
        "public_key": public_key_b64(),
        "value": sign_canonical(canonical),
        **_pq_fields(canonical),
    }


def object_signature(obj: dict[str, Any]) -> dict[str, str]:
    """Sign a discovery document in place of a manifest's structural canonical."""
    canonical = object_canonical(obj)
    return {
        "algorithm": "ed25519",
        "public_key": public_key_b64(),
        "value": sign_canonical(canonical),
        **_pq_fields(canonical),
    }
