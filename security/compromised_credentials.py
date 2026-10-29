"""Refuse restoring a credential already exposed in this repository's history.

Only SHA-256 fingerprints are kept here. This local safeguard cannot revoke a
provider credential; its owner must confirm revocation at the provider.
"""

from __future__ import annotations

import hashlib

# Historical data/config/model_providers.yaml, commits 88c0d7251 / 5a7116167.
# Plaintext is deliberately absent from source, reports, fixtures and logs.
COMPROMISED_SHA256 = frozenset({
    "ac4a4bc2fbcf39581b82ce8047d328ae63279c663ba46e62ccd096324feb7f8b",
    # Public Lottery v0.1.0 MESH_ADMIN_TOKEN.
    "5b023816d239f5431323c6eef7d07d3ba3af7c0f9a77a6009821b0d321f7378c",
})


def reject_compromised_credential(value: str | None) -> None:
    if value and hashlib.sha256(value.strip().encode("utf-8")).hexdigest() in COMPROMISED_SHA256:
        raise ValueError("This credential was exposed in repository history; configure a replacement and revoke the old credential")
