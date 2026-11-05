"""One stable pseudonym per buyer, for this hub's own providers: `X-AIMarket-Buyer-Ref`.

Some of the operator's own providers keep data that belongs to the buyer: Attested Memory's
`memory.write@v1` stores a Memory Unit that only its owner may read. They used to take the
owner from `X-Payment-Channel`, which carries a reference only when the buyer paid from a
payment channel. A buyer on hub credits (X-API-Key), on x402 or on a trial sent an empty
header, so every one of them became the same owner and could read the others' "private"
memories. The channel reference itself was no better as an owner: it is keyed with a salt
drawn per process (`peer_routing._BUYER_SALT`), so it changed on every hub restart.

This header names the buyer this hub actually authenticated, once per hub, forever:

- a credit account: an X-API-Key the ledger resolved;
- an agent spending a principal's account under a mandate: that agent for that principal, never the
  principal itself (the mandate delegates spending, not the principal's data);
- the wallet of a verified x402 payment;
- a payment channel, only when this call's price is held on it (its secret was checked).

A trial, a sandbox visitor or an unpaid anonymous call names nobody, and the header is left
out: a provider must then treat the call as anonymous, never as a shared default owner. So does
a call paid from someone else's subcontract allowance: the account it draws on is the root
buyer's, and the subcontractor holding the job token is not that buyer. So does a call another
hub routed here on its own credits or channel (X-AIMarket-Routing-Hub; the peer key a reselling
hub holds here): that account is the routing hub's, shared by all of its buyers, so naming it would
give every one of them one memory owner again. Only a verified x402 payment the buyer made still
names them on a routed call. (Found 2026-11-05 checking the Multica work for Vulnetix's classes; the
attested hub holds such an account for independentai.network, and no memory call had used it.)

The value is `bref-` + 32 hex characters of an HMAC under a key derived from this hub's
Ed25519 signing seed. So it is stable across restarts and rebuilds for as long as the hub
keeps its identity, cannot be linked across hubs, and does not reveal the account, key,
wallet or channel. It is sent only beside `X-AIMarket-Internal-Token`, to the operator's own
gateway hosts — a third-party seller never receives it.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

HEADER = "X-AIMarket-Buyer-Ref"
PREFIX = "bref-"
_LABEL = b"aimarket-hub/provider-buyer-ref/v1"


def _key(signer: Any) -> bytes | None:
    """The HMAC key, derived from the signing seed (never the seed itself), or None."""
    # Signer keeps its Ed25519 seed as `_seed` (32 bytes) on every hub version in service;
    # tests/test_provider_buyer_ref.py fails if that ever changes.
    seed = getattr(signer, "_seed", None)
    if not isinstance(seed, (bytes, bytearray)) or len(seed) != 32:
        return None
    return hmac.new(bytes(seed), _LABEL, hashlib.sha256).digest()


def buyer_identity(call: Any, local: Any) -> str:
    """The buyer this hub authenticated for this call, as `kind:id`, or "" for nobody."""
    if getattr(call, "sandbox_mode", False):
        return ""
    funding = getattr(call, "funding", None)
    job = getattr(funding, "job", None)
    if job is not None and getattr(job, "funded_by", "own") == "allowance":
        return ""
    routed = bool(getattr(call, "routed_by_hub", False))
    admission = getattr(funding, "admission", None)
    if admission is not None and not routed:
        principal = str(getattr(admission, "account_id", "") or "").strip()
        agent = str(getattr(admission, "agent", "") or "").strip()
        return f"mandate:{principal}:{agent}" if principal and agent else ""
    account = str(getattr(call, "credit_account", "") or "").strip()
    if account and not routed:
        return "credits:" + account
    accepted = getattr(local, "x402_accepted", None)
    wallet = str(getattr(call, "payer_wallet", "") or "").strip().lower()
    if wallet and isinstance(accepted, dict) and accepted.get("ok"):
        return "wallet:" + wallet
    channel = str(getattr(call, "x_payment_channel", "") or "").strip()
    if channel and not routed and getattr(local, "reserved", False) and getattr(local, "hold_rail", "") == "channel":
        return "channel:" + channel
    return ""


def buyer_ref(signer: Any, call: Any, local: Any) -> str:
    """The header value for this call, or "" when the buyer is anonymous."""
    identity = buyer_identity(call, local)
    if not identity:
        return ""
    key = _key(signer)
    if key is None:
        return ""
    return PREFIX + hmac.new(key, identity.encode(), hashlib.sha256).hexdigest()[:32]
