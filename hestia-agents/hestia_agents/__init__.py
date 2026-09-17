"""Deterministic capability providers for the HESTIA hearth.

Every agent here is a pure function of its payload: no clock, no randomness, no
network, no filesystem. That is not an aesthetic choice. HESTIA signs each
response with Ed25519 over the result, the capability id and the digest of the
input — and a signature over a value nobody else can reproduce proves nothing.
Determinism is what makes the receipt worth paying for.
"""

from __future__ import annotations

__version__ = "0.1.0"

AGENT_SLUGS = ("rules-decide", "json-canonical", "commit-referee")
