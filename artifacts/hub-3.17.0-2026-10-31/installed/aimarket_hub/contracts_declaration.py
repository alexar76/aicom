"""What this hub has ON CHAIN — published so a stranger can go and look.

A hub's ``/.well-known/ai-market.json`` used to say ``supported_chains: ["base"]``,
``payment_configured: true`` and a price list, and not one address. So "this hub settles
on Base" was a claim with nothing behind it: a reader could not open the escrow, could
not see a single transaction, and could not tell a hub that has been settling for months
from one switched on this morning. The only way to find out was to send it money.

This module publishes the two things that are checkable without trusting us at all:

  * ``escrow``  — the contract this hub settles payment channels through, and
  * ``wallet``  — the address its invoices are actually paid to,

plus the settlement token, each with the chain id and an explorer link. None of it is a
new disclosure: the escrow address appears in every channel open, and the recipient in
every x402 ``accepts[].payTo`` this hub has ever answered with. Publishing them only
means a reader no longer has to buy something to learn them.

**Nothing here is configured separately, deliberately.** The addresses are read from the
payment configuration and deployment registry the hub already runs with, so a hub that
deploys an escrow starts declaring it on its next request, and one that has none declares
nothing at all. There is no switch to forget and no second place to update — which is the
only reason the declaration can be trusted to still be true after a redeploy.

Two guards, because this is the one part of the well-known that names money:

*Realm seal.* Addresses come from :func:`chain_net.active_network`, which in the UNI
realm is the bubble's own Anvil deployment (``assert_sealed`` runs on every resolve).
:func:`realm.check_addresses` is called again on what we are about to publish, so a sealed
realm cannot publish a mainnet address even by accident.

*Readiness.* The wallet is published only when :attr:`HubConfig.payment_ready` — the same
condition that already gates ``payment_configured``. A hub that credits any ``tx_hash``
without checking it has no business pointing at a wallet as if money arriving there meant
anything.

The mirror side is :func:`sanitize`, which validates the same structure coming back from
somebody ELSE's well-known. A peer's declaration is a claim about addresses, and the whole
point is that a claim about an address is checkable — so it is stored and re-exported
verbatim-but-bounded, and verified against the chain by whoever draws it.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: Deployment-registry name -> the role it plays for a HUB. Only these reach the
#: well-known: the other nine contracts in the registry belong to the demo economy
#: (lottery, AMM, lending, audit pool …), not to this hub's settlement path, and a reader
#: sizing up a hub does not need them to check whether it can take money.
_ESCROW_NAMES: tuple[str, ...] = ("AIMarketEscrow",)
_TOKEN_NAMES: tuple[str, ...] = ("USDC", "USDT")

#: Bounds for a FOREIGN declaration (see :func:`sanitize`). Untrusted input: a peer could
#: hand us a thousand 4 KB "addresses" and we re-export whatever we store.
MAX_ENTRIES = 8
_MAX_STR = 120
_ALLOWED_ROLES = frozenset({"escrow", "wallet", "token", "registry", "lottery", "nft", "other"})


def _addr(value: Any) -> str:
    """An EVM address, or "" — nothing else may be published as one.

    Checked rather than trusted for our OWN addresses too: `AIMARKET_ESCROW_EVM_ADDRESS`
    is an env var, and an env var with a stray quote in it would otherwise be published as
    the hub's escrow and quietly fail every reader's on-chain check.
    """
    text = str(value or "").strip()
    if len(text) != 42 or not text.startswith("0x"):
        return ""
    try:
        int(text, 16)
    except ValueError:
        return ""
    if int(text, 16) == 0:  # the zero address is "unset", not a deployment
        return ""
    return text


def _explorer_address(explorer_tx: str, address: str) -> str:
    """Turn a ``…/tx/{}`` template into that chain's address page for `address`."""
    if not explorer_tx or not address:
        return ""
    base = explorer_tx.split("/tx/")[0] if "/tx/" in explorer_tx else explorer_tx.rstrip("/")
    return f"{base}/address/{address}"


def own_declaration(
    config: Any, *, payment_ready: bool | None = None
) -> dict[str, Any] | None:
    """This hub's on-chain declaration, or None when it has nothing on chain.

    None — not an empty block — so a hub with no escrow and no wallet stays silent instead
    of publishing a shape that reads like "checked, nothing there".
    """
    try:
        from aimarket_hub import chain_net, realm

        spec = chain_net.active_network()
    except Exception as exc:  # never break .well-known over a declaration
        logger.warning("contracts declaration: network unavailable (%s)", exc)
        return None

    addresses = spec.addresses or {}
    entries: list[dict[str, Any]] = []
    try:
        simulated = bool(realm.is_uni())
    except Exception:  # pragma: no cover - realm imported above
        simulated = False
    # The UNI realm clears chain id, RPCs and addresses but deliberately KEEPS the network's
    # name, so nothing inside the bubble notices it is not live. An explorer URL is not part
    # of that fiction: basescan.org/address/<anvil address> is a real page about a real chain
    # that has never heard of this contract. Publish no link rather than a wrong one.
    explorer_tx = "" if simulated else spec.explorer_tx

    def add(role: str, address: str, name: str, note: str = "") -> None:
        address = _addr(address)
        if not address or any(e["address"].lower() == address.lower() for e in entries):
            return
        entry: dict[str, Any] = {"role": role, "name": name, "address": address}
        explorer = _explorer_address(explorer_tx, address)
        if explorer:
            entry["explorer"] = explorer
        if note:
            entry["note"] = note
        entries.append(entry)

    # Escrow: ONLY what this hub is configured with. There is deliberately no fallback to
    # the deployment registry, even though the registry holds a perfectly good escrow for
    # the active chain — because that address belongs to whoever deployed it, not to
    # whoever reads the registry.
    #
    # The fallback existed for about an hour and its first act was to make
    # `hub.attestedmemory.net` — a hub with no escrow, no wallet and
    # `payment_configured: false` — publish AICOM's live Base escrow as its own settlement
    # contract. A reader would have verified that address, found a real contract with real
    # transactions, and concluded that this hub settles there. Precisely the lie this whole
    # feature exists to prevent, invented by the feature itself.
    #
    # An escrow is therefore an explicit operator decision (AIMARKET_ESCROW_EVM_ADDRESS),
    # and a hub that has not made it declares no escrow.
    add("escrow", str(getattr(config, "escrow_evm_address", "") or ""),
        "AIMarketEscrow", "payment channels are funded and settled here")

    # The address that DEBITS escrow channels. The contract binds a channel to whichever
    # authorized hub debits it first, and the buyer's EIP-712 DebitAuthorization must name
    # exactly that address — which is the bridge's signer, not the invoice wallet below.
    # Unpublished, a buyer could fund a channel and still not know what to sign.
    if entries:
        try:
            from aimarket_hub.escrow_bridge import config as bridge_config

            add("escrow_hub", str(bridge_config.hub_address() or ""), "escrow debit address",
                "debits escrow channels; a DebitAuthorization names this address as `hub`")
        except Exception:
            pass

    # The wallet, under the same readiness rule that gates `payment_configured`: pointing at
    # a recipient while skipping on-chain verification advertises money that is never checked.
    wallet_ready = (
        bool(getattr(config, "payment_ready", False))
        if payment_ready is None
        else bool(payment_ready)
    )
    if wallet_ready:
        add("wallet", str(getattr(config, "payment_recipient", "") or ""),
            "settlement wallet", "invoices for this hub are paid to this address")

    # The settlement token, and only if there IS a settlement path. A token address on its
    # own says nothing about this hub — USDC is USDC for everyone — so publishing one next
    # to no escrow and no wallet dresses an empty declaration up as a payment rail.
    if entries:
        for name in _TOKEN_NAMES:
            if name in addresses:
                add("token", addresses[name], name, "settlement token")

    if not entries:
        return None

    try:
        realm.check_addresses({e["name"]: e["address"] for e in entries})
    except Exception as exc:
        # A sealed realm about to name a real asset. Publish nothing rather than the leak.
        logger.error("contracts declaration suppressed by realm seal: %s", exc)
        return None

    declaration: dict[str, Any] = {"version": 1, "chain": spec.id, "entries": entries}
    if spec.chain_id is not None:
        declaration["chain_id"] = spec.chain_id
    if spec.display_name:
        declaration["network"] = spec.display_name
    explorer_base = explorer_tx.split("/tx/")[0] if "/tx/" in explorer_tx else ""
    if explorer_base:
        declaration["explorer"] = explorer_base
    if spec.testnet:
        # A testnet address looks exactly like a mainnet one. Unlabelled, it reads as real.
        #
        # Read from the NETWORK, not from `config.payment_testnet`. That flag advertises the
        # payment rail (it defaults to True until an operator sets AIFACTORY_PAYMENT_TESTNET=0)
        # and has nothing to say about where a contract is deployed — using it here labelled
        # the real Base escrow, at chain id 8453, as testnet.
        declaration["testnet"] = True
    if simulated:
        # The bubble publishes its own Anvil deployment, which is correct and sealed — but an
        # address and a chain id are not self-describing, and simulated money read as revenue
        # is the exact confusion this realm exists to prevent.
        declaration["simulated"] = True
    return declaration


def sanitize(raw: Any) -> dict[str, Any] | None:
    """Bound and validate a declaration read from someone ELSE's well-known.

    Everything that survives is either a real EVM address or dropped, so what we store and
    re-export can be handed straight to an RPC. Returns None when there is nothing usable —
    a peer that declares no contracts must not become a peer that declares an empty list.
    """
    if not isinstance(raw, dict):
        return None
    entries: list[dict[str, Any]] = []
    for item in (raw.get("entries") or [])[: MAX_ENTRIES * 4]:
        if not isinstance(item, dict) or len(entries) >= MAX_ENTRIES:
            continue
        address = _addr(item.get("address"))
        if not address or any(e["address"].lower() == address.lower() for e in entries):
            continue
        role = str(item.get("role") or "other").strip().lower()[:20]
        entry: dict[str, Any] = {
            "role": role if role in _ALLOWED_ROLES else "other",
            "name": str(item.get("name") or "")[:_MAX_STR],
            "address": address,
        }
        # An explorer URL travels to a browser. Only absolute http(s) — a `javascript:` or
        # `data:` "explorer" in a stranger's declaration is a click away from the operator.
        explorer = str(item.get("explorer") or "").strip()[:300]
        if explorer.startswith(("http://", "https://")):
            entry["explorer"] = explorer
        note = str(item.get("note") or "")[:_MAX_STR]
        if note:
            entry["note"] = note
        entries.append(entry)
    if not entries:
        return None

    out: dict[str, Any] = {"version": 1, "entries": entries}
    chain = str(raw.get("chain") or "").strip().lower()[:32]
    if chain:
        out["chain"] = chain
    try:
        chain_id = int(raw.get("chain_id"))
    except (TypeError, ValueError):
        chain_id = 0
    if 0 < chain_id < 2**53:
        out["chain_id"] = chain_id
    network = str(raw.get("network") or "").strip()[:_MAX_STR]
    if network:
        out["network"] = network
    explorer = str(raw.get("explorer") or "").strip()[:300]
    if explorer.startswith(("http://", "https://")):
        out["explorer"] = explorer
    if bool(raw.get("testnet")):
        out["testnet"] = True
    if bool(raw.get("simulated")):
        out["simulated"] = True
    return out


def addresses_of(declaration: Any) -> list[str]:
    """Just the addresses, for whoever wants to ask a chain about them."""
    if not isinstance(declaration, dict):
        return []
    return [
        e["address"] for e in (declaration.get("entries") or [])
        if isinstance(e, dict) and _addr(e.get("address"))
    ]
