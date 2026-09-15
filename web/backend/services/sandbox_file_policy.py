"""Block sensitive paths from public sandbox file serving."""

from __future__ import annotations

import os
from pathlib import PurePosixPath

_BLOCKED_BASENAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "credentials.json",
        "secrets.json",
        "service-account.json",
    }
)

_BLOCKED_SUFFIXES = (
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".pkcs12",
    ".kdbx",
    ".sqlite",
    ".db",
)

_BLOCKED_PREFIXES = (
    ".git/",
    ".ssh/",
    ".aws/",
    "node_modules/",
)


def sandbox_file_path_allowed(rel_path: str) -> bool:
    """Return False when the relative path must not be served via sandbox GET."""
    norm = rel_path.replace("\\", "/").lstrip("/")
    if not norm or norm.startswith("/"):
        return False
    parts = PurePosixPath(norm).parts
    if any(p in ("..", "") for p in parts):
        return False
    lower = norm.lower()
    base = os.path.basename(lower)
    if base in _BLOCKED_BASENAMES:
        return False
    if base.startswith(".env."):
        return False
    if lower.endswith(_BLOCKED_SUFFIXES):
        return False
    for prefix in _BLOCKED_PREFIXES:
        if lower.startswith(prefix) or f"/{prefix}" in lower:
            return False
    return True
