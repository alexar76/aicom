"""x402 Offer and Receipt extension — signed offers on a 402, a signed receipt after payment.

Implements `specs/extensions/extension-offer-and-receipt.md` (x402 Foundation, v0.6,
2026-02-04) in its JWS form:

* **Offer** — for every `accepts[]` entry of a 402, a JWS over the offer payload
  (`version`, `resourceUrl`, `scheme`, `network` (CAIP-2), `asset`, `payTo`, `amount`,
  `validUntil`), placed at ``extensions["offer-receipt"].info.offers[]`` with an unsigned
  ``acceptIndex``.
* **Receipt** — on a call that was paid and delivered, a JWS over the receipt payload
  (`version`, `network`, `resourceUrl`, `payer`, `issuedAt`), placed at
  ``extensions["offer-receipt"].info.receipt`` of the settlement response. Privacy-minimal
  by default, as the extension asks: no transaction hash inside the receipt (the
  settlement response around it carries the hash, as x402 always did).

JWS details, all from the extension and RFC 7515/8037: header ``{"alg": "EdDSA", "kid":
<did:key URL>}``, payload = the RFC 8785 (JCS) bytes of the payload object, compact
serialization, base64url without padding. The key is the hub's own Ed25519 signer — the key
its discovery document publishes as ``signer_public_key`` — so a verifier can establish
signer authorization (extension §4.5.1) by checking that the ``kid``'s key equals the
``signer_public_key`` served at the resource's origin under
``/.well-known/agent-marketplace`` (or ``/.well-known/ai-market.json``).

Nothing here touches money: the extension is a statement about terms and delivery, signed;
payment acceptance stays in ``x402`` and ``settle``.
"""
from __future__ import annotations

import base64
import json
import os
import time
from typing import Any

EXTENSION = "offer-receipt"
PAYLOAD_VERSION = 1

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

_OFFERS_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {"offers": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "format": {"type": "string", "const": "jws"},
            "acceptIndex": {"type": "integer"},
            "signature": {"type": "string", "description": "JWS compact serialization containing the offer payload"},
        },
        "required": ["format", "signature"],
    }}},
    "required": ["offers"],
}

_RECEIPT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {"receipt": {
        "type": "object",
        "properties": {
            "format": {"type": "string", "const": "jws"},
            "signature": {"type": "string", "description": "JWS compact serialization containing the receipt payload"},
        },
        "required": ["format", "signature"],
    }},
    "required": ["receipt"],
}


def enabled() -> bool:
    """On unless AIMARKET_X402_OFFER_RECEIPT is 0/false/off: the extension is additive, and a
    client that does not know it ignores ``extensions`` entries it does not recognise."""
    return os.environ.get("AIMARKET_X402_OFFER_RECEIPT", "1").strip().lower() not in {"0", "false", "off", "no"}


def offer_ttl_s() -> int:
    try:
        return max(60, int(os.environ.get("AIMARKET_X402_OFFER_TTL_S", "900")))
    except ValueError:
        return 900


# -- encodings ------------------------------------------------------------------------

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = _B58[r] + out
    pad = len(data) - len(data.lstrip(b"\x00"))
    return "1" * pad + out


def did_key(public_key: bytes) -> str:
    """did:key for an Ed25519 public key: multicodec 0xed01, base58btc, 'z' prefix."""
    if len(public_key) != 32:
        raise ValueError("an Ed25519 public key is 32 bytes")
    return "did:key:z" + _b58encode(b"\xed\x01" + public_key)


def did_key_url(public_key: bytes) -> str:
    did = did_key(public_key)
    return f"{did}#{did.split(':')[-1]}"


def _jcs(value: Any) -> bytes:
    """RFC 8785 bytes. The awr package is the canonicalizer every other signed document of
    this ecosystem uses (AWR receipts, mandates); a non-integer number is refused there,
    and nothing here signs one (amounts are strings by the extension's own schema)."""
    import awr

    return awr.jcs.canonicalize(value)


# -- JWS ------------------------------------------------------------------------------

def jws_sign(signer: Any, payload: dict[str, Any]) -> str:
    """Compact JWS, EdDSA, over the JCS bytes of ``payload``, with the signer's did:key as kid."""
    public_key = base64.b64decode(signer.public_key_b64)
    header = {"alg": "EdDSA", "kid": did_key_url(public_key)}
    signing_input = b64url(_jcs(header)) + "." + b64url(_jcs(payload))
    return signing_input + "." + b64url(signer.sign(signing_input.encode("ascii")))


def jws_verify(token: str, public_key: bytes) -> dict[str, Any] | None:
    """The payload when ``token`` is an EdDSA JWS by ``public_key`` whose kid names that key;
    None otherwise. Strict Ed25519 (no small-order keys or points) via the hub's verifier."""
    try:
        h64, p64, s64 = token.split(".")
        header = json.loads(b64url_decode(h64))
        if header.get("alg") != "EdDSA" or header.get("kid") != did_key_url(public_key):
            return None
        from aimarket_hub.signing import Signer

        ok = Signer.verify(base64.b64encode(public_key).decode(), base64.b64encode(b64url_decode(s64)).decode(),
                           f"{h64}.{p64}")
        if not ok:
            return None
        payload = json.loads(b64url_decode(p64))
        return payload if isinstance(payload, dict) else None
    except Exception:  # noqa: BLE001 — anything malformed is simply not a valid token
        return None


# -- offers ---------------------------------------------------------------------------

def offer_payload(entry: dict[str, Any], resource_url: str, *, network: str, valid_until: int) -> dict[str, Any]:
    """The signed offer for one accepts[] entry. V1 entries name the amount maxAmountRequired
    and the chain by bare string; the payload always carries ``amount`` and a CAIP-2
    ``network`` (extension §4.2)."""
    return {
        "version": PAYLOAD_VERSION,
        "resourceUrl": resource_url,
        "scheme": str(entry.get("scheme") or "exact"),
        "network": network,
        "asset": str(entry.get("asset") or ""),
        "payTo": str(entry.get("payTo") or ""),
        "amount": str(entry.get("amount") or entry.get("maxAmountRequired") or ""),
        "validUntil": int(valid_until),
    }


def offers_extension(signer: Any, accepts: list[dict[str, Any]], resource_url: str, *, network: str,
                     now: int | None = None) -> dict[str, Any] | None:
    """``{"offer-receipt": {"info": {"offers": [...]}, "schema": ...}}`` for these accepts."""
    if not accepts or not network:
        return None
    valid_until = int(now if now is not None else time.time()) + offer_ttl_s()
    offers = []
    for index, entry in enumerate(accepts):
        payload = offer_payload(entry, resource_url, network=network, valid_until=valid_until)
        if not (payload["asset"] and payload["payTo"] and payload["amount"]):
            continue
        offers.append({"format": "jws", "acceptIndex": index, "signature": jws_sign(signer, payload)})
    if not offers:
        return None
    return {EXTENSION: {"info": {"offers": offers}, "schema": _OFFERS_SCHEMA}}


# -- receipt --------------------------------------------------------------------------

def receipt_payload(*, network: str, resource_url: str, payer: str, issued_at: int,
                    transaction: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": PAYLOAD_VERSION,
        "network": network,
        "resourceUrl": resource_url,
        "payer": payer,
        "issuedAt": int(issued_at),
    }
    if transaction:
        payload["transaction"] = transaction
    return payload


def settlement_response(signer: Any, *, network: str, resource_url: str, payer: str, transaction: str,
                        now: int | None = None) -> dict[str, Any]:
    """The x402 SettlementResponse for a paid, delivered call, with the signed receipt in its
    ``extensions`` (extension §5.1). The hash stays in the response, out of the receipt."""
    receipt = jws_sign(signer, receipt_payload(
        network=network, resource_url=resource_url, payer=payer,
        issued_at=int(now if now is not None else time.time())))
    return {
        "success": True,
        "transaction": transaction,
        "network": network,
        "payer": payer,
        "extensions": {EXTENSION: {"info": {"receipt": {"format": "jws", "signature": receipt}},
                                   "schema": _RECEIPT_SCHEMA}},
    }


# -- AWR/2 settlement binding ---------------------------------------------------------
# awr/adoption/x402-receipt/PROFILE.md (AWR-X402/1): the x402 receipt, verbatim, as the
# `credentialSubject.settlement` of the call's AWR/2 WorkReceipt (AWR/2 §10.3).

AWR_SCHEME = "x402-offer-receipt-v1"


def _jws_header_payload(token: Any) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Header and payload of a compact JWS, unverified; None when it is not one."""
    try:
        h64, p64, _ = token.split(".")
        header, payload = json.loads(b64url_decode(h64)), json.loads(b64url_decode(p64))
    except Exception:  # noqa: BLE001
        return None
    return (header, payload) if isinstance(header, dict) and isinstance(payload, dict) else None


def awr_settlement(settlement: Any) -> dict[str, Any] | None:
    """The AWR-X402/1 binding for a SettlementResponse built by ``settlement_response``; None
    when it carries no JWS receipt. ``transaction`` stays out, as it stays out of the x402
    receipt (extension §5.2): the binding is as privacy-minimal as the receipt it carries."""
    if not isinstance(settlement, dict):
        return None
    receipt = (((settlement.get("extensions") or {}).get(EXTENSION) or {}).get("info") or {}).get("receipt") or {}
    token = receipt.get("signature") if isinstance(receipt, dict) else None
    parts = _jws_header_payload(token) if receipt.get("format") == "jws" else None
    if parts is None:
        return None
    payload = parts[1]
    return {"scheme": AWR_SCHEME, "network": payload.get("network"),
            "resourceUrl": payload.get("resourceUrl"), "receipt": token}


def check_awr_settlement(binding: Any, issuer_public_key: bytes | None = None) -> list[str]:
    """The AWR-X402/1 §3 checks, offline. Returns the result codes: AWR-X402-001..003 are
    errors, 004 (``issuer-unbound``) and 005 (``transaction`` not checked) warnings; an
    empty list is a clean binding whose receipt key is the work receipt's issuer key."""
    import awr

    if not isinstance(binding, dict) or binding.get("scheme") != AWR_SCHEME:
        return ["AWR-X402-001"]

    def key_of(token: Any) -> tuple[bytes, dict[str, Any]] | None:
        parts = _jws_header_payload(token)
        if parts is None or parts[0].get("alg") != "EdDSA":
            return None
        kid = parts[0].get("kid")
        if not isinstance(kid, str) or "#" not in kid:
            return None
        try:
            key = awr.didkey.parse_did_key(kid.split("#", 1)[0])
        except Exception:  # noqa: BLE001
            return None
        return (key, parts[1]) if did_key_url(key) == kid else None

    receipt = key_of(binding.get("receipt"))
    if receipt is None:
        return ["AWR-X402-001"]
    offer = key_of(binding["offer"]) if "offer" in binding else None
    if "offer" in binding and offer is None:
        return ["AWR-X402-001"]
    codes: list[str] = []
    payload = jws_verify(binding["receipt"], receipt[0])
    offer_payload_ = jws_verify(binding["offer"], offer[0]) if offer else None
    if payload is None or payload.get("version") != PAYLOAD_VERSION or (offer and offer_payload_ is None):
        return ["AWR-X402-002"]
    same = (payload.get("network") == binding.get("network")
            and payload.get("resourceUrl") == binding.get("resourceUrl"))
    if offer_payload_ is not None:
        valid_until = int(offer_payload_.get("validUntil") or 0)
        same = (same and offer_payload_.get("network") == payload.get("network")
                and offer_payload_.get("resourceUrl") == payload.get("resourceUrl")
                and (valid_until == 0 or valid_until >= int(payload.get("issuedAt") or 0)))
    if not same:
        codes.append("AWR-X402-003")
    if issuer_public_key is None or receipt[0] != issuer_public_key:
        codes.append("AWR-X402-004")
    if binding.get("transaction"):
        codes.append("AWR-X402-005")
    return codes
