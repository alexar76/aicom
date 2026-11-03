"""Buyer-confirmed deliveries: the evidence behind "this seller really delivers".

A seller paid directly by the buyer (x402 on the seller's own route) is out of this hub's sight:
the hub routed the free quote, never the money, and must not hold the seller's books. What it
can do is count evidence that a BUYER chooses to bring:

- a receipt the seller signed with the key its own listing published (``provider_pubkey``,
  from the peer's signed manifest), saying it delivered (or refunded) the payment with this
  EIP-3009 nonce;
- the transaction that moved USDC under that very authorization, from the payer to the seller
  (for a refund: from the seller's refund wallet back to the payer), checked on chain by the
  same ``settle.verify_transfer`` that decides whether a seller-direct call was paid.

What is kept is a counter, not the books: the seller, the kind, when, and a hash of the payer
so distinct buyers can be counted. No amount, no address, no transaction in the clear. One
transaction counts once.

What it is not: a quality guarantee. A seller can buy from itself through other wallets, and
the facilitator pays the gas, so confirmations can be inflated at little cost. Distinct buyers
are counted for that reason, and the number is published as evidence of real deliveries.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Callable

KINDS = ("delivery", "refund")
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
_NONCE = re.compile(r"^0x[0-9a-fA-F]{64}$")
_PRODUCT = re.compile(r"^[A-Za-z0-9_.:@-]{1,128}$")
_CAPABILITY = re.compile(r"^[a-z0-9_.-]{1,96}@v[0-9]+$")


class DeliveryError(ValueError):
    """The evidence does not hold; the message says what. ``status`` is the HTTP answer."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def canonical(receipt: dict[str, Any]) -> str:
    """The bytes a seller signs: sorted keys, no spaces, UTF-8 as is (the kit's canonicalJson)."""
    return json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def check_receipt(receipt: Any) -> dict[str, Any]:
    """The receipt's shape. Raises DeliveryError naming the field that is wrong."""
    if not isinstance(receipt, dict):
        raise DeliveryError("receipt must be an object")
    if receipt.get("v") != 1:
        raise DeliveryError("receipt.v must be 1")
    kind = receipt.get("kind")
    if kind not in KINDS:
        raise DeliveryError(f"receipt.kind must be one of {', '.join(KINDS)}")
    if not _PRODUCT.match(str(receipt.get("product_id") or "")):
        raise DeliveryError("receipt.product_id is missing or malformed")
    if not _CAPABILITY.match(str(receipt.get("capability") or "")):
        raise DeliveryError("receipt.capability must look like name.verb@v1")
    chain_id = receipt.get("chain_id")
    if not ((type(chain_id) is int and chain_id == 8453)
            or (isinstance(chain_id, str) and chain_id == "8453")):
        raise DeliveryError("receipt.chain_id must be 8453 (Base)")
    need = ("payer", "pay_to", "nonce") if kind == "delivery" else ("payer", "refund_from", "refund_nonce")
    for key in need:
        pattern = _NONCE if key.endswith("nonce") else _ADDRESS
        if not pattern.match(str(receipt.get(key) or "")):
            raise DeliveryError(f"receipt.{key} is missing or malformed")
    return receipt


@dataclass
class Confirmation:
    id: str
    source_hub: str
    product_id: str
    kind: str
    buyer_hash: str


def confirm(
    receipt: Any,
    signature: Any,
    transaction: Any,
    *,
    listings: list[Any],
    verify_signature: Callable[[str, str, str], bool],
    verify_transfer: Callable[..., dict[str, Any]],
    terms_factory: Callable[[str], Any],
    max_age_s: int = 30 * 86400,
) -> Confirmation:
    """Check one buyer's evidence and return what to count. Raises DeliveryError.

    ``listings``: this hub's capabilities with the receipt's product_id. The one whose
    ``provider_pubkey`` verifies the signature is the seller; a key no listing published proves
    nothing about any seller here.
    """
    r = check_receipt(receipt)
    sig = str(signature or "")
    tx = str(transaction or "").strip().lower()
    if not sig:
        raise DeliveryError("signature is required: the seller's Ed25519 signature over the receipt")
    if not re.match(r"^0x[0-9a-f]{64}$", tx):
        raise DeliveryError("transaction must be the 0x hash of the payment (or refund) on Base")
    text = canonical(r)
    seller = next((c for c in listings
                   if (getattr(c, "provider_pubkey", "") or "").strip()
                   and verify_signature(c.provider_pubkey.strip(), sig, text)), None)
    if seller is None:
        raise DeliveryError("no listing on this hub published the key that signed this receipt", status=404)

    # The money, on chain: the authorization over this nonce moved USDC to the right wallet.
    if r["kind"] == "delivery":
        pay_to, nonce, signer_of_payment = r["pay_to"], r["nonce"], r["payer"]
    else:
        pay_to, nonce, signer_of_payment = r["payer"], r["refund_nonce"], r["refund_from"]
    try:
        facts = verify_transfer(tx_hash=tx, terms=terms_factory(pay_to), require_nonce=nonce.lower(), max_age_s=max_age_s)
    except Exception as exc:   # PaymentError / PaymentFinal: the chain does not back the claim (yet)
        raise DeliveryError(f"the transaction does not back this receipt: {exc}") from exc
    if str(facts.get("authorizer") or "").lower() != signer_of_payment.lower():
        raise DeliveryError("the transfer was authorized by another wallet than the receipt names")

    payer = r["payer"].lower()
    return Confirmation(
        id=hashlib.sha256(f"{r['kind']}|{tx}".encode()).hexdigest(),
        source_hub=seller.source_hub,
        product_id=seller.product_id,
        kind=r["kind"],
        buyer_hash=hashlib.sha256(f"aimarket-delivery/v1|{payer}".encode()).hexdigest(),
    )
