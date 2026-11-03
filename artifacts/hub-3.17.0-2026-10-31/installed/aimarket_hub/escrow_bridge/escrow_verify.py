"""C1 — decide whether an on-chain escrow channel backs the credit being asked for.

This replaces "somebody paid the platform wallet, and the caller says it was them" with
"the contract itself says this depositor locked these funds in this channel". It is a
pure read: no keys, no writes, nothing to broadcast.

Two properties come for free, both of which the transfer path had to work for:

* The depositor is bound BY CONSTRUCTION. ``channels[channelId].depositor`` is whoever
  called ``openChannel``; there is no inbound-transfer hash for a bystander to quote, so
  the theft vector that forced the EIP-191 payer proof onto the transfer path simply does
  not exist here.
* A refund is the CONTRACT's job. Escrowed funds are still the depositor's until a debit
  is submitted, so the remainder does not become an operator IOU the way it does when a
  deposit is a plain transfer to the platform's own wallet.

What this module does NOT establish is exclusivity: one escrow channel must still fund at
most one ledger channel, system-wide. That is the shared claim registry's job, and
:func:`claim_identifier` explains how an escrow channel is named inside it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from aimarket_hub.escrow_bridge import chain, config
from aimarket_hub.escrow_bridge.eip712 import Eip712Error, addresses_equal, normalize_address
from aimarket_hub.escrow_bridge.errors import (
    ChannelNotOnChain,
    EscrowStateRejected,
)

logger = logging.getLogger(__name__)

# The escrow refuses to whitelist a token whose decimals() != 6 (it reverts
# UnsupportedTokenDecimals in its constructor and in setTokenWhitelist), and its
# MIN_DEPOSIT/MAX_DEPOSIT constants are 6-decimal literals. So every token that can
# legally appear in a channel is on this scale, and the conversion below is exact.
TOKEN_DECIMALS = 6
_UNITS_PER_CENT = 10 ** (TOKEN_DECIMALS - 2)

# A claim identifier prefix that cannot collide with a transaction hash. Both a channelId
# and a tx hash are 32-byte hex, so feeding a raw channelId to the shared registry would
# put them in ONE namespace — and a depositor could then choose channelId == some victim's
# pending funding tx hash and block that victim's transfer-funded open before it happens.
# The registry leaves non-hex identifiers byte-exact, so a prefix keeps the two spaces
# disjoint while still giving escrow channels single-use semantics.
CLAIM_PREFIX = "escrow-channel:"


def claim_identifier(channel_id: str) -> str:
    """How this escrow channel is named in the shared single-use deposit registry.

    The FUNDING EVENT for an escrow channel is ``openChannel(channelId, …)``, not a
    transfer, so the thing that may be consumed exactly once is the channelId — there is
    no meaningful tx hash to key on (and the same channel could be quoted from two hub
    opens). Lower-cased because the id is hex and case carries no information.
    """
    return f"{CLAIM_PREFIX}{str(channel_id or '').strip().lower()}"


def usd_to_base_units(usd: float) -> int:
    """USD → token base units via integer cents, rounding UP.

    Cents first because the ledger's own unit is the cent; rounding up means the on-chain
    escrow must cover at least what the ledger will credit, never a hair less.
    """
    import math

    if usd is None:
        raise EscrowStateRejected("deposit amount is required")
    try:
        value = float(usd)
    except (TypeError, ValueError) as exc:
        raise EscrowStateRejected(f"deposit amount is not a number: {usd!r}") from exc
    if not math.isfinite(value) or value <= 0:
        raise EscrowStateRejected(f"deposit amount must be finite and positive, got {usd!r}")
    # round(.., 6) first strips binary-float noise (5.00 * 100 == 499.99999999999994)
    # so an exact-cent amount is not pushed up a whole cent.
    cents = max(1, math.ceil(round(value * 100, 6)))
    return cents * _UNITS_PER_CENT


def base_units_to_usd(units: int) -> float:
    return int(units) / (100 * _UNITS_PER_CENT)


@dataclass(frozen=True)
class EscrowFunding:
    """A verified escrow channel, and what it may back."""

    channel: chain.EscrowChannel
    required_units: int
    claim_id: str
    chain_id: int
    escrow_address: str

    @property
    def backed_usd(self) -> float:
        """What the on-chain balance could cover, for reporting alongside the credit."""
        return base_units_to_usd(self.channel.balance)

    def as_dict(self) -> dict[str, object]:
        return {
            "escrow": self.escrow_address,
            "chain_id": self.chain_id,
            "required_units": self.required_units,
            "claim_id": self.claim_id,
            "backed_usd": self.backed_usd,
            **self.channel.as_dict(),
        }


def _expected_token_address() -> str:
    """Address the operator's configured payment token resolves to, or "" if unknown.

    The contract's own whitelist is the hard gate (owner-gated, and it enforces the
    6-decimal scale), so an unresolvable symbol is a reason to log, not to refuse — but
    when we CAN resolve it, a channel funded in a different token is a real mismatch
    between what the hub prices in and what the buyer locked.
    """
    import os

    symbol = (os.environ.get("AIMARKET_PAYMENT_TOKEN", "USDC") or "USDC").strip().upper()
    try:
        spec = chain._network()
    except Exception:
        return ""
    addr = (spec.addresses or {}).get(symbol, "")
    try:
        return normalize_address(addr) if addr else ""
    except Eip712Error:
        return ""


def verify_funding(
    *,
    channel_id: str,
    claimed_wallet: str,
    deposit_usd: float,
    now: float | None = None,
) -> EscrowFunding:
    """Verify an escrow channel backs ``deposit_usd`` for ``claimed_wallet``.

    Raises on every rejection (never returns a "not really verified" object), so a caller
    that forgets to check a boolean cannot credit by accident. ChainUnavailable propagates
    from the read: an unreadable chain is not a verification.
    """
    required = usd_to_base_units(deposit_usd)
    try:
        wallet = normalize_address(claimed_wallet)
    except Eip712Error as exc:
        raise EscrowStateRejected(f"claimed wallet is not an EVM address: {exc}") from exc

    escrow = chain.escrow_address()
    cid = chain.chain_id()                      # also cross-checks RPC vs configured network
    ch = chain.read_channel(channel_id, address=escrow)

    if not ch.exists:
        raise ChannelNotOnChain(
            f"no escrow channel {channel_id[:14]}… at {escrow} — the depositor must call "
            "openChannel before the hub can credit it"
        )
    if not ch.is_open:
        raise EscrowStateRejected(
            f"escrow channel is {ch.status_name}, not Open — it cannot back a new credit"
        )
    if not addresses_equal(ch.depositor, wallet):
        # The wallet the caller claims must be the wallet the CONTRACT recorded. This is
        # the whole point of reading the chain instead of trusting a submitted hash.
        raise EscrowStateRejected(
            "escrow depositor does not match the claimed wallet — the channel belongs to "
            "another address"
        )
    if ch.expired(now=now):
        raise EscrowStateRejected(
            "escrow channel has already expired on chain; anyone may settle it, so it "
            "cannot back a credit"
        )
    if ch.balance < required:
        raise EscrowStateRejected(
            f"escrow balance {base_units_to_usd(ch.balance):.6f} does not cover the "
            f"requested {base_units_to_usd(required):.6f}"
        )
    if ch.used_amount:
        # A partially consumed escrow channel is already backing an off-chain ledger
        # channel somewhere. Funding a second one from it would double-credit the
        # remainder, and the claim registry only guards the FIRST claim.
        raise EscrowStateRejected(
            "escrow channel already has on-chain debits — it is already backing a "
            "settled ledger channel and cannot fund another"
        )

    expected_token = _expected_token_address()
    if expected_token and not addresses_equal(ch.token, expected_token):
        raise EscrowStateRejected(
            "escrow channel is funded in a different token than this hub prices in"
        )
    if not expected_token:
        logger.warning(
            "escrow token %s not cross-checked: the configured payment symbol does not "
            "resolve to an address on this network (the contract whitelist still applies)",
            ch.token,
        )

    hub = config.hub_address()
    if hub and ch.hub_bound and not addresses_equal(ch.hub, hub):
        # The contract binds `hub` on the first debit and refuses any other caller
        # afterwards. If it is already bound to somebody else, this hub can never debit
        # the channel — crediting it would sell service we could never collect for.
        raise EscrowStateRejected(
            "escrow channel is already bound to a different hub and can never be debited "
            "by this one"
        )

    return EscrowFunding(
        channel=ch, required_units=required, claim_id=claim_identifier(channel_id),
        chain_id=cid, escrow_address=escrow,
    )
