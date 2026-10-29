"""Hybrid Ed25519 + ML-DSA-65 signing for SKOPOS Hub federation (manifest + pubkey).

Canonical form matches ``aimarket_hub.signing.Signer.manifest_canonical`` so a
crawler can verify. Persist the key under the SKOPOS data dir (compose volume
``/app/.skopos``) so a rebuild does not mint a new identity.

That canonical form is why SKOPOS has its own signer rather than using
``oracle_core.Signer`` — it signs the HUB's shape, with ``by_hub``, not this
package's. Only the post-quantum half is shared, and it is IMPORTED rather than
reimplemented: the field names (``pq_value`` / ``pq_algorithm`` /
``pq_public_key``) are the interoperability contract, and a second spelling of
them is a signature no verifier in the ecosystem looks at. The ML-DSA key is
written beside the classical one as ``<key path>_mldsa``, on the same volume, so
enabling PQ never touches the Ed25519 identity a peer already pinned.

Phase 2 (sign hybrid) is on with ``ORACLE_PQC=1``. Phase 3 is verifiers refusing
a document with no ``pq_*`` — which is what this unblocks: SKOPOS was one of the
signers still classical-only, so requiring PQ on the hubs would have rejected it.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
from pathlib import Path
from typing import Any

try:
    from dilithium_py.ml_dsa import ML_DSA_65 as _MLDSA

    _PQ_LIB = True
except Exception:  # pragma: no cover
    _MLDSA = None
    _PQ_LIB = False


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def _read_pq_keypair(path: Path) -> tuple[bytes, bytes]:
    try:
        lines = path.read_text().splitlines()
        if len(lines) != 2 or not all(lines):
            raise ValueError("expected exactly two non-empty hex lines")
        pair = (bytes.fromhex(lines[0]), bytes.fromhex(lines[1]))
        if not all(pair):
            raise ValueError("empty key")
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"ML-DSA key file {path} is corrupted: {exc}") from exc
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)
    return pair


def _load_or_make_pq(path: Path) -> tuple[bytes, bytes]:
    if path.exists():
        return _read_pq_keypair(path)
    if not _PQ_LIB:
        raise RuntimeError(
            "ORACLE_PQC is on but dilithium-py is missing — "
            "install aimarket-oracle-core[pqc] on this signer"
        )
    pk, sk = _MLDSA.keygen()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = f"{pk.hex()}\n{sk.hex()}\n"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return _read_pq_keypair(path)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(payload)
    except Exception:
        with contextlib.suppress(OSError):
            path.unlink()
        raise
    return pk, sk


def _local_load_pq_keypair(
    key_path: str | Path, *, pqc: bool | None = None
) -> tuple[bytes, bytes] | None:
    """Same contract as ``oracle_core.signing.load_pq_keypair`` (``{path}_mldsa``)."""
    if pqc is None:
        pqc = _truthy(os.environ.get("ORACLE_PQC"))
    if not pqc:
        return None
    if not _PQ_LIB:
        raise RuntimeError(
            "ORACLE_PQC is on but dilithium-py is missing — "
            "install aimarket-oracle-core[pqc] on this signer"
        )
    return _load_or_make_pq(Path(f"{key_path}_mldsa"))


def _local_pq_fields(pair: tuple[bytes, bytes] | None, canonical: str) -> dict[str, str]:
    if pair is None:
        return {}
    pk, sk = pair
    return {
        "pq_algorithm": "ml-dsa-65",
        "pq_public_key": base64.b64encode(pk).decode(),
        "pq_value": base64.b64encode(_MLDSA.sign(sk, canonical.encode())).decode(),
    }


try:
    # Prefer the shared helpers when the installed oracle-core exports them (monorepo /
    # post-0.3.0). PyPI 0.3.0 still has hybrid Signer but not these symbols — ImportError
    # then, NOT a silent classical stub: that would report ORACLE_PQC=1 while emitting
    # phase-1 signatures and break the phase-3 rollout this module exists to unblock.
    from oracle_core.signing import load_pq_keypair as _load_pq_keypair
    from oracle_core.signing import pq_fields as _pq_fields
except ImportError:  # pragma: no cover - PyPI ≤0.3.0 or slimmed install
    _load_pq_keypair = _local_load_pq_keypair
    _pq_fields = _local_pq_fields

def _ensure_keypair(path: Path) -> tuple[bytes, bytes]:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if path.exists():
        raw = path.read_bytes()
        if len(raw) == 64:
            return raw[:32], raw[32:]
        raise RuntimeError(f"Ed25519 key file {path} is corrupted (size={len(raw)})")
    path.parent.mkdir(parents=True, exist_ok=True)
    priv = Ed25519PrivateKey.generate()
    seed = priv.private_bytes_raw()
    pub = priv.public_key().public_bytes_raw()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raw = path.read_bytes()
        if len(raw) == 64:
            return raw[:32], raw[32:]
        raise RuntimeError(f"Ed25519 key file {path} is corrupted (size={len(raw)})")
    try:
        os.write(fd, seed + pub)
    finally:
        os.close(fd)
    return seed, pub


def _seed_from_env() -> bytes | None:
    raw = os.environ.get("SKOPOS_SIGNING_SEED_B64", "").strip()
    if not raw:
        return None
    seed = base64.b64decode(raw)
    if len(seed) != 32:
        raise RuntimeError("SKOPOS_SIGNING_SEED_B64 must decode to a 32-byte seed")
    return seed


class Signer:
    def __init__(self, key_path: str | Path | None = None) -> None:
        path = Path(
            key_path
            or os.environ.get("SKOPOS_SIGNING_KEY_PATH")
            or ".skopos/aimarket_signing_key"
        )
        self.key_path = path
        env_seed = _seed_from_env()
        if env_seed is not None:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

            self._seed = env_seed
            self._pub_bytes = (
                Ed25519PrivateKey.from_private_bytes(env_seed).public_key().public_bytes_raw()
            )
        else:
            self._seed, self._pub_bytes = _ensure_keypair(self.key_path)
        self._public_key_b64 = base64.b64encode(self._pub_bytes).decode()
        # Resolve the ML-DSA key once — it is a file read, and a manifest is signed per
        # request. None when ORACLE_PQC is off, which is still phase 1 and still valid.
        self._pq = _load_pq_keypair(self.key_path)

    @property
    def public_key_b64(self) -> str:
        return self._public_key_b64

    def sign_canonical(self, canonical: str) -> str:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        sig = Ed25519PrivateKey.from_private_bytes(self._seed).sign(canonical.encode())
        return base64.b64encode(sig).decode()

    def manifest_canonical(self, manifest: dict[str, Any]) -> str:
        tools = manifest.get("tools", [])
        tools_hash = hashlib.sha256(
            json.dumps(tools, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        by_hub_hash = hashlib.sha256(
            json.dumps(manifest.get("by_hub", {}), sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        return (
            f"capabilities_count:{manifest.get('capabilities_count', 0)}"
            f"|generated_at:{manifest.get('generated_at', '')}"
            f"|protocol_version:{manifest.get('protocol_version', 'v1')}"
            f"|tools_hash:{tools_hash}"
            f"|by_hub_hash:{by_hub_hash}"
        )

    def sign_manifest(self, manifest: dict[str, Any]) -> dict[str, str]:
        canonical = self.manifest_canonical(manifest)
        signature = {
            "algorithm": "ed25519",
            "public_key": self.public_key_b64,
            "value": self.sign_canonical(canonical),
        }
        signature.update(_pq_fields(self._pq, canonical))
        return signature


_signer: Signer | None = None


def get_signer(key_path: str | Path | None = None) -> Signer:
    global _signer
    if key_path is not None:
        return Signer(key_path=key_path)
    if _signer is None:
        _signer = Signer()
    return _signer


__all__ = ["Signer", "get_signer"]
