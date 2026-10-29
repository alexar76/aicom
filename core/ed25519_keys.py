"""Persist Ed25519 identities without exposing seeds or racing other workers."""

from __future__ import annotations

import hmac
import os
import stat
import tempfile
import time
from contextlib import suppress
from pathlib import Path

from security.signing_key_storage import reject_compromised_keypair


def _private_key_type():
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError as exc:
        # There is no HMAC substitute for an asymmetric signature. In particular,
        # publishing a random seed as its "public key" discloses the signing key.
        raise RuntimeError("Ed25519 signing requires cryptography") from exc
    return Ed25519PrivateKey


def _validated_keypair(raw: bytes) -> tuple[bytes, bytes]:
    key_type = _private_key_type()
    if len(raw) != 64:
        raise RuntimeError("Invalid Ed25519 identity file; explicit recovery is required")
    seed, public = raw[:32], raw[32:]
    derived = key_type.from_private_bytes(seed).public_key().public_bytes_raw()
    if not hmac.compare_digest(derived, public):
        raise RuntimeError("Ed25519 identity public key does not match its private key")
    reject_compromised_keypair(raw)
    return seed, public


def _read_keypair(path: Path) -> tuple[bytes, bytes]:
    # Refuse links and devices rather than following an identity-file replacement.
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeError("Ed25519 identity must be a regular file")
        # Another worker may still be removing its exclusive publish staging
        # link. Persistent links to an external inode must never be chmod'ed.
        for _ in range(20):
            if info.st_nlink == 1:
                break
            time.sleep(0.005)
            info = os.fstat(fd)
        if info.st_nlink != 1:
            raise RuntimeError("Ed25519 identity must not have external hardlinks")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            raw = handle.read(65)
        pair = _validated_keypair(raw)
        os.fchmod(fd, 0o600)
        return pair
    finally:
        os.close(fd)


def load_or_create_ed25519_keypair(
    path: Path, *, legacy_path: Path | None = None,
) -> tuple[bytes, bytes]:
    """Read the existing seed+public identity, or atomically create it with mode 0600.

    Publishing a fully written temporary inode with link() never replaces an
    identity another worker created. A malformed existing file is never rotated
    silently: peers pin this public key and existing receipts rely on it.
    """
    key_type = _private_key_type()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        return _read_keypair(path)
    except FileNotFoundError:
        pass
    if legacy_path is not None:
        try:
            pair = _read_keypair(legacy_path)
        except FileNotFoundError:
            pair = None
    else:
        pair = None
    if pair is None:
        private = key_type.generate()
        pair = (private.private_bytes_raw(), private.public_key().public_bytes_raw())
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(pair[0] + pair[1])
            handle.flush()
            os.fsync(handle.fileno())
        # Link creation is atomic and exclusive; persist the directory entry
        # before acknowledging an identity used to sign durable receipts.
        with suppress(FileExistsError):
            os.link(temporary, path)
        os.unlink(temporary)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return _read_keypair(path)
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temporary)
