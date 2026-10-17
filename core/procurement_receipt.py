"""Verify the Hub v1/v2 billing receipt; it does not sign the diagnosis text."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from datetime import datetime

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.procurement_store import micros

_V2 = ("type", "channel_id", "category", "plugin", "reason", "verify_score",
       "delivery_reasons", "trace_id", "refunded")


# Ed25519 points of small order (orders 1, 2, 4, 8; sign bit cleared), as libsodium checks them.
# `cryptography` (OpenSSL) accepts, under such a key, a signature valid for EVERY message, and no
# secret exists for these keys; a key that arrives from someone else is refused if it is one. 2026-10-12.
_ED25519_SMALL_ORDER = frozenset(bytes.fromhex(h) for h in (
    "0000000000000000000000000000000000000000000000000000000000000000",
    "0100000000000000000000000000000000000000000000000000000000000000",
    "26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc05",
    "c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac037a",
    "ecffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f",
    "edffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f",
    "eeffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f",
))


def _strict_ed25519_key(raw: bytes) -> bytes:
    if len(raw) == 32 and (raw[:31] + bytes([raw[31] & 0x7F])) in _ED25519_SMALL_ORDER:
        raise ValueError("small-order Ed25519 public key")
    return raw


def verify_signature(signature: dict, public_key: str, pq_key: str, canonical: str) -> None:
    if signature.get("algorithm") != "ed25519":
        raise ValueError("unsupported signature algorithm")
    Ed25519PublicKey.from_public_bytes(_strict_ed25519_key(base64.b64decode(public_key, validate=True))).verify(
        base64.b64decode(signature["value"], validate=True), canonical.encode())
    if pq_key or signature.get("pq_value"):
        from dilithium_py.ml_dsa import ML_DSA_65

        if not pq_key or signature.get("pq_public_key") != pq_key \
                or signature.get("pq_algorithm") != "ml-dsa-65" \
                or not ML_DSA_65.verify(base64.b64decode(pq_key, validate=True), canonical.encode(),
                                       base64.b64decode(signature.get("pq_value", ""), validate=True)):
            raise ValueError("missing or invalid pinned post-quantum signature")


def check_hub_document(body: dict, public_key: str, pq_key: str) -> None:
    canonical = json.dumps({k: v for k, v in body.items() if k != "signature"},
                           sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    verify_signature(body["signature"], public_key, pq_key, canonical)


def checked_charge(receipt: dict, public_key: str, request: dict, created: float, pq_key: str = "") -> int:
    signature = receipt.get("signature")
    if not isinstance(signature, dict):
        raise ValueError("unsupported receipt signature")
    version = signature.get("version", 1)
    if version not in (1, 2) or not receipt.get("nonce") or receipt.get("success") is not True:
        raise ValueError("unsupported or unsuccessful receipt")
    if any(receipt.get(k) != request[k] for k in ("product_id", "capability_id")):
        raise ValueError("receipt supplier mismatch")
    when = datetime.fromisoformat(str(receipt["timestamp"]).replace("Z", "+00:00")).timestamp()
    if when < created - 5 or when > time.time() + 30:
        raise ValueError("receipt predates this purchase")
    charge = micros(receipt["price_usd"])
    canonical = (f"nonce:{receipt.get('nonce', '')}|product_id:{receipt.get('product_id', '')}"
                 f"|capability_id:{receipt.get('capability_id', '')}|price_usd:{receipt.get('price_usd', 0)}"
                 f"|timestamp:{receipt.get('timestamp', '')}|success:1|latency_ms:{receipt.get('latency_ms', 0)}")
    if version == 2:
        fields = json.dumps({k: receipt.get(k) for k in _V2}, sort_keys=True, ensure_ascii=False,
                            separators=(",", ":"), default=str).encode()
        canonical += "|v:2|fields:" + hashlib.sha256(fields).hexdigest()
    verify_signature(signature, public_key, pq_key, canonical)
    return charge
