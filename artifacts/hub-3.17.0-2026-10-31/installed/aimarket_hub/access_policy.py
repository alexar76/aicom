"""Honest catalogue access labels.

Price and access are separate dimensions.  In particular, a provider may publish a zero
price to mean "not sold through federation" while requiring an operator credential.  Such a
row is discoverable, but it is not a public free offer and must never be rendered as one.
"""

from __future__ import annotations

from typing import Any

PUBLIC_FREE = "public_free"
PAID = "paid"
OPERATOR_GATED = "operator_gated"

_OPERATOR_MARKERS = (
    "operator-gated:",
    "operator gated:",
    "published unpriced rather than sold",
)


def capability_access_mode(capability: Any) -> str:
    """Return a small, protocol-safe access mode for a capability-like object.

    New providers may expose ``access_mode`` explicitly.  The description fallback keeps
    older signed manifests honest; MOMUS used the exact marker before the structured field
    existed.  Unknown zero-priced rows remain public-free for backward compatibility.
    """
    explicit = str(getattr(capability, "access_mode", "") or "").strip().lower()
    if explicit in {PUBLIC_FREE, PAID, OPERATOR_GATED}:
        return explicit

    description = str(getattr(capability, "description", "") or "").lower()
    if any(marker in description for marker in _OPERATOR_MARKERS):
        return OPERATOR_GATED

    price = float(getattr(capability, "price_per_call_usd", 0.0) or 0.0)
    return PAID if price > 0 else PUBLIC_FREE


def capability_is_publicly_offerable(capability: Any) -> bool:
    return capability_access_mode(capability) != OPERATOR_GATED
