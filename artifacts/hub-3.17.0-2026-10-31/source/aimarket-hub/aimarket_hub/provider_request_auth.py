"""Sign the calls this hub admits, so the provider can tell they came from here.

A provider built on oracle-core can now refuse a priced capability to any caller that
is not a hub it trusts (``oracles/core/oracle_core/price_gate.py``). Before that, the
provider's own URL was a second door with no lock on it: on 2026-10-16 an unpaid
``POST`` straight to GAIA or SYMMARTYS got the full $0.002 answer that this hub sells
for $0.002.

This module writes the five headers that gate reads. They say "this hub, at this
time, admitted exactly this capability with exactly this input, addressed to this
invoke URL", signed with the hub's federation key (the ``signer_public_key`` of its
well-known, which the provider pins). The wire format is defined in price_gate.py and
copied here, because the hub does not depend on oracle-core. Both sides pin the same
test vector (``tests/test_provider_request_auth.py`` and
``oracles/core/tests/test_price_gate.py``), so neither can drift alone.

When the hub signs, and why only then:

* a LOCAL listing with an ``invoke_url``: always. The hub's own paywall or trial has
  run before the provider is called; there is no other way to reach that call.
* a FEDERATED peer: only one this hub sells for (``AIMARKET_SELLS_FOR``). There the
  hub is the seller of record and has taken the price or a trial. For a peer it only
  brokers, the peer bills the buyer itself, and a signature would tell a gated peer
  "already paid" for a call nobody paid for.

``AIMARKET_SIGN_PROVIDER_REQUESTS=0`` turns it off. Signing never fails a call: on
any error the headers are left out and the provider decides what an unsigned call
gets.

The payer statement (aimarket-hub-payer/v1)
-------------------------------------------
The admission says the call was paid; it does not say by whom. A provider that hands
something to one buyer (GAIA leases a plug to whoever paid for its "on" and refuses
anyone else's "off" until the auto-off) needs the payer, and a caller's own headers
cannot be it: anyone can type a channel id or a wallet. So the hub states the payer it
verified, signed with the same key over the same call (``gaia/gaia/payer_identity.py``
defines the format and is the reference; both sides pin one golden vector):

    X-AIMarket-Hub-Payer            0x + 40 hex (lowercased) or base58, exactly
    X-AIMarket-Hub-Payer-Rail       channel | x402
    X-AIMarket-Hub-Payer-Signature  Ed25519 over "aimarket-hub-payer/v1\\n" + sorted
                                    compact JSON {aud, capability_id, hub, input_sha256,
                                    nonce, payer, rail, ts}

It reuses the admission's signer, audience, timestamp and nonce, read back from what
:func:`signed_headers` returned, so a statement belongs to exactly one admitted call.

Only a payer the hub checked: the x402 ``authorization.from`` the chain settled, or the
wallet that proved control of a channel's deposit when it was opened. A trial, hub
credits or a demo-credit channel has no payer, so no statement.

Only for the capabilities that need one (``AIMARKET_PAYER_STATEMENT_CAPABILITIES``,
default ``gaia.actuate@v1``). The hub tells providers an opaque buyer id and a channel
reference, never the buyer's wallet (``_opaque_buyer``, ``_provider_channel_ref`` in
api.py); a statement on every call would hand every provider every buyer's wallet.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

DOMAIN = "aimarket-hub-request/v1"

HUB_HEADER = "X-AIMarket-Hub-Signer"
AUDIENCE_HEADER = "X-AIMarket-Hub-Audience"
TIMESTAMP_HEADER = "X-AIMarket-Hub-Timestamp"
NONCE_HEADER = "X-AIMarket-Hub-Nonce"
SIGNATURE_HEADER = "X-AIMarket-Hub-Signature"

ENABLE_ENV = "AIMARKET_SIGN_PROVIDER_REQUESTS"
# Not "X-AIMarket-Hub": subcontracting already sends that name to local providers (the job
# token's issuer, aimarket_hub/subcontract.py), and these headers must never overwrite it.

PAYER_DOMAIN = "aimarket-hub-payer/v1"
PAYER_HEADER = "X-AIMarket-Hub-Payer"
PAYER_RAIL_HEADER = "X-AIMarket-Hub-Payer-Rail"
PAYER_SIGNATURE_HEADER = "X-AIMarket-Hub-Payer-Signature"
PAYER_RAILS = ("channel", "x402")
PAYER_CAPABILITIES_ENV = "AIMARKET_PAYER_STATEMENT_CAPABILITIES"
DEFAULT_PAYER_CAPABILITIES = ("gaia.actuate@v1",)

_EVM = re.compile(r"0x[0-9a-fA-F]{40}")
# '0' is not in the base58 alphabet, so an EVM address can never also match this.
_BASE58 = re.compile(r"[1-9A-HJ-NP-Za-km-z]{32,44}")


def enabled() -> bool:
    return (os.getenv(ENABLE_ENV) or "1").strip().lower() not in ("0", "false", "no", "off")


def normalize_url(url: str) -> str:
    """Same rule as oracle_core.price_gate.normalize_url; both sides compare after it."""
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError:
        return ""
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if scheme not in ("http", "https") or not host:
        return ""
    if ":" in host:
        host = f"[{host}]"
    if port is not None and (scheme, port) not in (("http", 80), ("https", 443)):
        host = f"{host}:{port}"
    return f"{scheme}://{host}{parts.path.rstrip('/')}"


def input_sha256(input_payload: Any) -> str:
    """The digest supply_security._bound_response_canonical binds: sorted, compact JSON."""
    raw = json.dumps(input_payload or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def request_canonical(
    *, hub: str, audience: str, capability_id: str, input_digest: str, timestamp: int, nonce: str,
) -> str:
    body = json.dumps(
        {
            "aud": normalize_url(audience),
            "capability_id": capability_id,
            "hub": normalize_url(hub),
            "input_sha256": input_digest,
            "nonce": nonce,
            "ts": int(timestamp),
        },
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return f"{DOMAIN}\n{body}"


def signed_headers(
    signer: Any,
    *,
    hub_url: str,
    audience: str,
    capability_id: str,
    input_payload: Any,
    now: float | None = None,
) -> dict[str, str]:
    """The five headers for one admitted call, or ``{}`` when off or when anything fails."""
    if not enabled():
        return {}
    hub, aud = normalize_url(hub_url), normalize_url(audience)
    if not hub or not aud:
        return {}
    try:
        ts = int(time.time() if now is None else now)
        nonce = secrets.token_hex(16)
        canonical = request_canonical(
            hub=hub, audience=aud, capability_id=str(capability_id or ""),
            input_digest=input_sha256(input_payload), timestamp=ts, nonce=nonce,
        )
        signature = signer.sign_canonical(canonical)
    except Exception:  # noqa: BLE001 — a signing fault must not fail the buyer's call
        logger.exception("provider request signing failed for %s; sending it unsigned", capability_id)
        return {}
    return {
        HUB_HEADER: hub,
        AUDIENCE_HEADER: aud,
        TIMESTAMP_HEADER: str(ts),
        NONCE_HEADER: nonce,
        SIGNATURE_HEADER: signature,
    }


# ── The payer statement ──────────────────────────────────────────────────────────


def payer_statement_wanted(capability_id: str) -> bool:
    """Whether calls of this capability carry the payer. Unset: the default list; empty: none."""
    raw = os.getenv(PAYER_CAPABILITIES_ENV)
    wanted = DEFAULT_PAYER_CAPABILITIES if raw is None else tuple(
        c.strip() for c in raw.split(",") if c.strip())
    return str(capability_id or "") in wanted


def normalize_payer(raw: Any) -> str:
    """Same rule as gaia.payer_identity.normalize_identity: EVM lowercased (EIP-55 case is a
    checksum, not another address), base58 exactly as written (its case is the address)."""
    s = str(raw if raw is not None else "").strip()
    if _EVM.fullmatch(s):
        return s.lower()
    if _BASE58.fullmatch(s):
        return s
    raise ValueError("the payer is not a wallet address (0x + 40 hex, or base58)")


def payer_canonical(
    *, hub: str, audience: str, capability_id: str, input_digest: str, timestamp: int, nonce: str,
    payer: str, rail: str,
) -> str:
    body = json.dumps(
        {
            "aud": normalize_url(audience),
            "capability_id": capability_id,
            "hub": normalize_url(hub),
            "input_sha256": input_digest,
            "nonce": nonce,
            "payer": normalize_payer(payer),
            "rail": rail,
            "ts": int(timestamp),
        },
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return f"{PAYER_DOMAIN}\n{body}"


def payer_headers(
    signer: Any,
    admission: Mapping[str, str],
    *,
    capability_id: str,
    input_payload: Any,
    payer: str,
    rail: str,
) -> dict[str, str]:
    """The three statement headers for the call ``admission`` admitted, or ``{}``.

    ``admission`` is what :func:`signed_headers` returned for this call: its signer, audience,
    timestamp and nonce are the statement's too, and ``input_payload`` must be the input it
    bound. ``{}`` when there is no admission or no payer, when the capability does not need
    one, or on any error: a statement left out makes the buyer anonymous, it never fails the
    call.
    """
    if not admission or not payer or not payer_statement_wanted(capability_id):
        return {}
    try:
        if rail not in PAYER_RAILS:
            raise ValueError(f"rail must be one of {', '.join(PAYER_RAILS)}")
        who = normalize_payer(payer)
        canonical = payer_canonical(
            hub=admission[HUB_HEADER], audience=admission[AUDIENCE_HEADER],
            capability_id=str(capability_id or ""), input_digest=input_sha256(input_payload),
            timestamp=int(admission[TIMESTAMP_HEADER]), nonce=admission[NONCE_HEADER],
            payer=who, rail=rail,
        )
        signature = signer.sign_canonical(canonical)
    except Exception:  # noqa: BLE001 — a statement fault must not fail the buyer's call
        logger.exception("payer statement failed for %s; sending the call without one", capability_id)
        return {}
    return {PAYER_HEADER: who, PAYER_RAIL_HEADER: rail, PAYER_SIGNATURE_HEADER: signature}
