"""What a hub publishes about its own money, and what it re-exports about a peer's.

`.well-known/ai-market.json` used to say `supported_chains: ["base"]` and
`payment_configured: true` with no address anywhere in the document, so the only way to
find out whether a hub had ever settled anything was to send it money. The escrow and the
settlement wallet are already visible to anyone who transacts here (every channel open
names the escrow; every x402 `accepts[].payTo` names the wallet), so publishing them
discloses nothing new — it just means a reader can check first.

The tests that matter here are the ones about NOT publishing: a sealed realm must never
name a real asset, a hub that credits any tx_hash must not point at a wallet as if money
arriving there were verified, and a bubble must not hand out explorer links to a chain
that has never heard of its contracts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from aimarket_hub import contracts_declaration as cd

ESCROW = "0xa4cb6ef73B982B847fB06Ec75540d05D0311B2Eb"
WALLET = "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a"
REAL_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
ANVIL_ESCROW = "0x5FbDB2315678afecb367f032d93F642f64180aa3"


@dataclass
class FakeConfig:
    escrow_evm_address: str = ""
    payment_recipient: str = ""
    payment_ready: bool = False
    payment_testnet: bool = False


@pytest.fixture(autouse=True)
def _live_realm(monkeypatch):
    """Default to a live Base hub; the UNI tests set their own realm."""
    for name in ("AIMARKET_CHAIN_REALM", "AIMARKET_TESTNET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AIMARKET_CHAIN", "base")
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")
    yield


def _by_role(declaration):
    return {e["role"]: e for e in (declaration or {}).get("entries", [])}


# ── own declaration ────────────────────────────────────────────────────────────


def test_only_the_escrow_the_hub_is_CONFIGURED_with_is_published():
    """The live hub's escrow is an env var, and that is the only source."""
    out = cd.own_declaration(FakeConfig(escrow_evm_address=ANVIL_ESCROW))
    assert _by_role(out)["escrow"]["address"] == ANVIL_ESCROW


def test_a_hub_with_no_escrow_never_borrows_one_from_the_registry():
    """Caught in production, one hour after this feature shipped.

    `hub.attestedmemory.net` has no escrow, no wallet and `payment_configured: false`. With
    a registry fallback it published AICOM's live Base escrow as its own settlement
    contract — and a reader would have verified that address, found a real contract with
    real transactions, and concluded this hub settles there. The exact lie the feature
    exists to prevent, invented by the feature itself.
    """
    out = cd.own_declaration(FakeConfig())
    assert out is None


def test_a_token_alone_is_not_a_payment_rail():
    """USDC is USDC for everyone: an address that says nothing about THIS hub must not
    dress an empty declaration up as a settlement path."""
    assert cd.own_declaration(FakeConfig()) is None
    with_escrow = cd.own_declaration(FakeConfig(escrow_evm_address=ESCROW))
    assert "token" in _by_role(with_escrow), "with a real settlement path, name the token"


def test_the_wallet_is_published_only_when_payments_are_actually_verified():
    """`payment_ready` is the same gate as `payment_configured`: a hub that credits any
    tx_hash without checking it has no business pointing at a wallet."""
    stub = cd.own_declaration(FakeConfig(payment_recipient=WALLET, payment_ready=False))
    assert "wallet" not in _by_role(stub)

    ready = cd.own_declaration(FakeConfig(payment_recipient=WALLET, payment_ready=True))
    assert _by_role(ready)["wallet"]["address"] == WALLET


def test_chain_id_network_and_explorer_travel_with_the_addresses():
    out = cd.own_declaration(FakeConfig(escrow_evm_address=ESCROW))
    assert out["chain_id"] == 8453
    assert out["chain"] == "base"
    assert out["explorer"] == "https://basescan.org"
    assert _by_role(out)["escrow"]["explorer"].endswith(f"/address/{ESCROW}")


def test_a_malformed_env_address_is_not_published_as_an_escrow():
    """AIMARKET_ESCROW_EVM_ADDRESS is an env var; a stray quote in it must not become
    this hub's published escrow and fail every reader's on-chain check."""
    assert cd.own_declaration(FakeConfig(escrow_evm_address='"0xnot-an-address"')) is None


def test_the_zero_address_counts_as_unset():
    assert cd.own_declaration(FakeConfig(
        escrow_evm_address="0x" + "0" * 40, payment_recipient="0x" + "0" * 40,
        payment_ready=True,
    )) is None


def test_a_hub_with_nothing_on_chain_publishes_no_block_at_all():
    """None, not an empty block: a shape that reads like 'checked, nothing there' is worse
    than silence."""
    assert cd.own_declaration(FakeConfig()) is None


def test_testnet_comes_from_the_NETWORK_not_from_the_payment_flag():
    """`payment_testnet` advertises the payment rail and defaults to True until an operator
    clears it — using it here labelled the real Base escrow, on chain 8453, as testnet."""
    out = cd.own_declaration(FakeConfig(payment_testnet=True, escrow_evm_address=ESCROW))
    assert out["chain_id"] == 8453
    assert "testnet" not in out


# ── realm seal ────────────────────────────────────────────────────────────────


def test_the_bubble_publishes_its_own_deployment_and_says_it_is_simulated(monkeypatch):
    monkeypatch.setenv("AIMARKET_CHAIN_REALM", "uni")
    monkeypatch.setenv("AIMARKET_RPC_BASE", "http://127.0.0.1:8546")
    out = cd.own_declaration(FakeConfig(escrow_evm_address=ANVIL_ESCROW))
    assert out["chain_id"] == 31337
    assert out["simulated"] is True
    assert _by_role(out)["escrow"]["address"] == ANVIL_ESCROW


def test_the_bubble_publishes_no_explorer_links(monkeypatch):
    """basescan.org/address/<anvil address> is a real page about a chain that has never
    heard of this contract. No link is better than a wrong one."""
    monkeypatch.setenv("AIMARKET_CHAIN_REALM", "uni")
    monkeypatch.setenv("AIMARKET_RPC_BASE", "http://127.0.0.1:8546")
    out = cd.own_declaration(FakeConfig(escrow_evm_address=ANVIL_ESCROW))
    assert "explorer" not in out
    assert all("explorer" not in e for e in out["entries"])


def test_a_sealed_realm_naming_a_real_asset_publishes_nothing(monkeypatch):
    monkeypatch.setenv("AIMARKET_CHAIN_REALM", "uni")
    monkeypatch.setenv("AIMARKET_RPC_BASE", "http://127.0.0.1:8546")
    monkeypatch.setenv("AIMARKET_ADDR_BASE_USDC", REAL_USDC)
    assert cd.own_declaration(FakeConfig()) is None


# ── sanitize: a peer's declaration, re-exported ───────────────────────────────


def _peer_declaration(**over):
    base = {
        "version": 1, "chain": "base", "chain_id": 8453, "network": "Base",
        "explorer": "https://basescan.org",
        "entries": [{"role": "escrow", "name": "AIMarketEscrow", "address": ESCROW}],
    }
    base.update(over)
    return base


def test_a_peer_declaration_survives_sanitising():
    out = cd.sanitize(_peer_declaration())
    assert out["entries"][0]["address"] == ESCROW
    assert out["chain_id"] == 8453


def test_a_peer_cannot_re_export_a_javascript_explorer_through_us():
    out = cd.sanitize(_peer_declaration(entries=[
        {"role": "escrow", "address": ESCROW, "explorer": "javascript:alert(1)"},
    ]))
    assert "explorer" not in out["entries"][0]


def test_a_peer_cannot_flood_our_well_known():
    out = cd.sanitize(_peer_declaration(entries=[
        {"role": "escrow", "address": "0x" + f"{i:040x}", "name": "x" * 9_000}
        for i in range(1, 60)
    ]))
    assert len(out["entries"]) == cd.MAX_ENTRIES
    assert json.dumps(out).__len__() < 4_000


def test_a_peer_that_declares_nothing_produces_no_declaration():
    """"" and {} both mean "this peer has not declared anything" — which is also what
    CLEARS a stale declaration on the next crawl."""
    assert cd.sanitize(None) is None
    assert cd.sanitize({}) is None
    assert cd.sanitize({"entries": [{"address": "0x0"}]}) is None


def test_addresses_of_returns_only_real_addresses():
    assert cd.addresses_of(_peer_declaration()) == [ESCROW]
    assert cd.addresses_of({"entries": [{"address": "nope"}]}) == []
    assert cd.addresses_of(None) == []


def test_the_escrow_debit_address_is_published_next_to_the_escrow(monkeypatch):
    """A buyer signs a DebitAuthorization naming the debiting hub; it must be able to read it."""
    signer = "0xBE0bBE44cceCfEb048dd53f601C37525a3D6C5f1"
    monkeypatch.setenv("AIMARKET_ESCROW_HUB_ADDRESS", signer)
    out = cd.own_declaration(FakeConfig(escrow_evm_address=ANVIL_ESCROW))
    assert _by_role(out)["escrow_hub"]["address"] == signer


def test_no_escrow_means_no_escrow_debit_address(monkeypatch):
    monkeypatch.setenv("AIMARKET_ESCROW_HUB_ADDRESS", "0xBE0bBE44cceCfEb048dd53f601C37525a3D6C5f1")
    out = cd.own_declaration(FakeConfig())
    assert out is None or "escrow_hub" not in _by_role(out)
