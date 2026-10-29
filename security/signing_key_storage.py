"""Private signing identities and explicit revocation of publicly exposed keys.

This dependency-free helper is mirrored inside independently shipped Hub/oracle
packages. The mirror regression checks keep the implementations identical.
Existing invalid or compromised identities are refused, never silently rotated.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import stat
import tempfile
import time
from contextlib import suppress
from pathlib import Path

# SHA-256 only; no private bytes or reconstructible seeds are embedded here.
# Confirmed in public alexar76/aicom and aimarket-plugins history on 2026-10-25.
COMPROMISED_PRIVATE_SHA256 = frozenset({
    "df4d28848d0541fe371e6a6b82b6c3f5c71b874cabc547b2864ec443832584e4",
    "39f031936ed3066aa7c647861a0db3622c2047b8f8426a057b29f1a65b33d6f3",
    "7623f31052756773e34f692b6f90a3cbe93d51d9666edb68473b0f56bfb1945b",
    "02c2c8322c51829a26b04b45e864a5df842e1efc1bf6abf361d6002b9aeca448",
    "dc7ea68d59012eb84f09d6982c06263a6b563d511ba34054b88656c9d4fcd555",
})
COMPROMISED_PUBLIC_SHA256 = frozenset({
    "eeb965e872fcc5704244ac2dc5b249596c176e434fe35c6055afa7a8e240f465",
    "98c782c47485fbafc5ad269982d47e4eb48e5d3723274ad4294bb3791cf0e5e9",
    "59e06ad12bdfe6c691668b63f4a7c5a20f62c5c3b7ff9564d3601abf6b2df304",
    "933590d1e764af4a81c2350d2c8d88d39c6a0107ee707c006007a2520aa02024",
})


def compromised_public_key(public: bytes) -> bool:
    return hashlib.sha256(public).hexdigest() in COMPROMISED_PUBLIC_SHA256


def reject_compromised_keypair(raw: bytes) -> None:
    if hashlib.sha256(raw).hexdigest() in COMPROMISED_PRIVATE_SHA256 or (
        len(raw) == 64 and compromised_public_key(raw[32:])
    ):
        raise RuntimeError(
            "Compromised Ed25519 signing identity: its private key was publicly exposed. "
            "Explicit identity recovery and peer trust reconciliation are required; no key was rotated."
        )


def validate_ed25519_keypair(raw: bytes) -> tuple[bytes, bytes]:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if len(raw) != 64:
        raise RuntimeError("Invalid Ed25519 identity file (expected 64 bytes); explicit recovery is required")
    seed, public = raw[:32], raw[32:]
    derived = Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes_raw()
    if not hmac.compare_digest(derived, public):
        raise RuntimeError("Ed25519 identity file does not hold the key: public key does not match its private key")
    reject_compromised_keypair(raw)
    return seed, public


def _read_private(path: Path, validator):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise RuntimeError("Unsafe or unreadable signing identity file") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeError("Signing identity must be a private regular file")
        # An exclusive publish briefly has its staging hardlink too. Allow that
        # writer to unlink it; persistent external hardlinks remain forbidden.
        for _ in range(20):
            if info.st_nlink == 1:
                break
            time.sleep(0.005)
            info = os.fstat(fd)
        if info.st_nlink != 1:
            raise RuntimeError("Signing identity must not have external hardlinks")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            raw = handle.read(1_048_577)
        if len(raw) > 1_048_576:
            raise RuntimeError("Signing identity exceeds size limit")
        pair = validator(raw)
        # Validate before touching permissions: a refused identity is preserved.
        os.fchmod(fd, 0o600)
        return pair
    finally:
        os.close(fd)


def _publish_exclusive(path: Path, payload: bytes) -> None:
    """Publish a complete 0600 inode only if no other worker already won."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        with suppress(FileExistsError):
            os.link(temporary, path)
        # Remove the staging link before validation's hardlink check.
        os.unlink(temporary)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temporary)


def load_or_create_ed25519_keypair(path: Path, *, legacy_path: Path | None = None) -> tuple[bytes, bytes]:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    path = Path(path)
    try:
        return _read_private(path, validate_ed25519_keypair)
    except FileNotFoundError:
        pass
    pair = None
    if legacy_path is not None:
        try:
            pair = _read_private(Path(legacy_path), validate_ed25519_keypair)
        except FileNotFoundError:
            pass
    if pair is None:
        private = Ed25519PrivateKey.generate()
        pair = (private.private_bytes_raw(), private.public_key().public_bytes_raw())
    _publish_exclusive(path, pair[0] + pair[1])
    return _read_private(path, validate_ed25519_keypair)


def read_ed25519_keypair(path: Path) -> tuple[bytes, bytes]:
    """Read and validate an identity without ever creating or replacing it."""
    return _read_private(Path(path), validate_ed25519_keypair)


def load_or_create_private_bytes(path: Path, generate, validate):
    """Load validated private material or publish a complete new 0600 file.

    Existing malformed, linked or compromised files fail closed. Parent
    directories are operator-trusted, as for signing identity paths.
    """
    path = Path(path)
    try:
        return _read_private(path, validate)
    except FileNotFoundError:
        pass
    payload = generate()
    validate(payload)
    _publish_exclusive(path, payload)
    return _read_private(path, validate)


def load_or_create_mldsa_keypair(path: Path, algorithm) -> tuple[bytes, bytes]:
    """Read the existing matching ML-DSA pair, or privately publish a new pair."""
    path = Path(path)

    def validate(raw: bytes):
        try:
            lines = raw.decode("ascii").splitlines()
            if len(lines) != 2 or not all(lines):
                raise ValueError("expected two non-empty lines")
            public, private = (bytes.fromhex(line) for line in lines)
            message = b"signing-identity-storage-integrity-v1"
            if not algorithm.verify(public, message, algorithm.sign(private, message)):
                raise ValueError("identity halves do not match")
            return public, private
        except Exception:
            raise RuntimeError("Invalid ML-DSA identity file; explicit recovery is required") from None

    try:
        return _read_private(path, validate)
    except FileNotFoundError:
        pass
    public, private = algorithm.keygen()
    _publish_exclusive(path, f"{public.hex()}\n{private.hex()}\n".encode("ascii"))
    return _read_private(path, validate)
