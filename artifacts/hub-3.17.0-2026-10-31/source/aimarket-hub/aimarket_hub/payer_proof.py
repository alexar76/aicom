"""The payer-proof challenge and its recovery, for a hub with no web app behind it.

Proving a deposit is two questions, and a standalone hub could answer neither. The first —
"did this transaction really pay us" — is :mod:`aimarket_hub.deposit_verify`. This module
is the second: **who controls the paying wallet**.

Why it matters (PAYAUTH-003b): the payer's address is printed in the very transaction a
claimant is quoting, so "the wallet I claim equals the wallet that paid" is satisfied by
anyone who can read the chain. Whoever calls ``channel/open`` receives the channel secret
and the invoke path authorises debits on that secret alone — so without a signature a
front-runner spends the victim's whole deposit and the victim is then locked out by the
single-use guard.

Both halves of the scheme live in ``web…on_chain`` and both degrade to "unproven" when
that package is missing: ``payer_proof_challenge`` returned ``""`` and
``_recover_payer_address`` returned ``None``, so a standalone hub refused every
deposit-funded channel *even with a working deposit verifier*. Fixing only the verifier
would have moved the refusal one step later.

**The message must be byte-identical to the canonical one**, or a signature accepted at the
web door is rejected at this one. It is reproduced here rather than imported, and
``tests/test_payer_proof.py`` asserts the two agree whenever both are importable.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: Verbatim from `web.backend.services.ai_market_protocol.on_chain`. Changing any of these
#: invalidates every signature already in flight, so they are versioned, not edited.
PAYER_PROOF_DOMAIN = "AIMarket-Payer-Proof"
PAYER_PROOF_VERSION = 1
PAYER_PROOF_CHANNEL_OPEN = "channel-open"

_HEX_DIGITS = set("0123456789abcdefABCDEF")


def canonical_proof_chain(chain: str) -> str:
    """Chain ids are ASCII and case-free."""
    return (chain or "").strip().lower()


def canonical_proof_tx_hash(tx_hash: str) -> str:
    """Canonical transaction id: hex is case-insensitive, base58 is not.

    The ``0x`` prefix is normalised IN, not merely lowercased — the two stacks disagreed
    about whether they had stripped it, and produced different preimages for one deposit.
    """
    tx = (tx_hash or "").strip()
    body = tx[2:] if tx[:2].lower() == "0x" else tx
    if body and all(c in _HEX_DIGITS for c in body):
        return "0x" + body.lower()
    return tx


def canonical_proof_payer(payer: str) -> str:
    """EIP-55 mixed case is a checksum, not identity, so an EVM address is lowercased."""
    addr = (payer or "").strip()
    if len(addr) == 42 and addr[:2].lower() == "0x":
        body = addr[2:]
        if all(c in _HEX_DIGITS for c in body):
            return "0x" + body.lower()
    return addr


def canonical_proof_amount_cents(amount_usd: Any) -> int:
    """The integer cents both ledgers bill in; -1 for anything unusable.

    -1 keeps the challenge deterministic while guaranteeing a proof over it can never
    match a real deposit.
    """
    try:
        value = float(amount_usd)
    except (TypeError, ValueError):
        return -1
    if value != value or value in (float("inf"), float("-inf")):
        return -1
    return int(round(value * 100))


def channel_open_proof_message(
    *, chain: str, tx_hash: str, payer: str, amount_usd: Any
) -> str:
    """The exact EIP-191 text the paying wallet signs to claim a channel deposit.

    Personal-sign on purpose: every ordinary wallet can produce it with no typed-data
    support, which is what makes it usable from an SDK, a browser extension and a
    hardware wallet alike.
    """
    return (
        f"{PAYER_PROOF_DOMAIN}/v{PAYER_PROOF_VERSION}\n"
        f"purpose:{PAYER_PROOF_CHANNEL_OPEN}\n"
        f"chain:{canonical_proof_chain(chain)}\n"
        f"tx:{canonical_proof_tx_hash(tx_hash)}\n"
        f"payer:{canonical_proof_payer(payer)}\n"
        f"amount_cents:{canonical_proof_amount_cents(amount_usd)}"
    )


def recover_channel_open_payer(
    *, chain: str, tx_hash: str, payer: str, amount_usd: Any, signature: str
) -> str | None:
    """Address that signed the canonical challenge, or None on ANY failure.

    None means "unproven", and the caller refuses to credit — so a deployment that cannot
    evaluate a proof never grants one.
    """
    if not (signature or "").strip():
        return None
    try:
        from eth_account import Account
        from eth_account.messages import encode_defunct

        message = channel_open_proof_message(
            chain=chain, tx_hash=tx_hash, payer=payer, amount_usd=amount_usd
        )
        return Account.recover_message(
            encode_defunct(text=message), signature=signature.strip()
        )
    except Exception as exc:
        logger.error("Hub-native payer proof recovery failed: %s — treating as unproven", exc)
        return None
