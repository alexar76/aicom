"""One deposit, one claim — whatever chain label a door uses (channels.claim_deposit_exclusive).

The registry keyed a claim on the caller's label, while AIMARKET_DEPOSIT_RPC_URL verifies every
label on the same node: one transfer opened a channel as "base" and another as "ethereum".
"""
from __future__ import annotations

import pytest

from aimarket_hub import channels, deposit_verify

TX = "0x" + "5a" * 32


@pytest.fixture
def one_node(monkeypatch):
    monkeypatch.setenv("AIMARKET_DEPOSIT_RPC_URL", "http://deposit-node.test")
    monkeypatch.setattr(deposit_verify, "_rpc_chain_id", lambda url, timeout=5.0: 8453)


@pytest.mark.parametrize("registry", ["web", "hub-local"])
def test_one_node_one_claim_across_labels(monkeypatch, one_node, registry):
    if registry == "hub-local":
        monkeypatch.setattr(channels, "_shared_on_chain", lambda attr: None)
    first = channels._claim_deposit_shared(chain="base", tx_hash=TX, channel_id="ch_a", amount_cents=500)
    again = channels._claim_deposit_shared(chain="ethereum", tx_hash=TX.upper().replace("0X", "0x"),
                                           channel_id="ch_b", amount_cents=500)
    assert first["ok"] is True
    assert again["ok"] is False and again["error"] == "already_claimed"


def test_the_labels_name_the_chain_the_node_serves(one_node):
    labels = channels.deposit_registry_labels("ethereum")
    assert labels[0] == "eip155:8453" and "ethereum" in labels and "base" in labels


def test_without_an_override_labels_of_different_chains_do_not_collide(monkeypatch):
    monkeypatch.delenv("AIMARKET_DEPOSIT_RPC_URL", raising=False)
    assert channels._claim_deposit_shared(chain="base", tx_hash=TX, channel_id="c1", amount_cents=1)["ok"] is True
    # Ethereum mainnet is another chain: the same hash there is another transaction.
    assert channels._claim_deposit_shared(chain="ethereum", tx_hash=TX, channel_id="c2", amount_cents=1)["ok"] is True


def test_a_node_whose_chain_cannot_be_read_fails_closed(monkeypatch):
    monkeypatch.setenv("AIMARKET_DEPOSIT_RPC_URL", "http://down.test")
    monkeypatch.setattr(deposit_verify, "_rpc_chain_id", lambda url, timeout=5.0: None)
    got = channels._claim_deposit_shared(chain="base", tx_hash=TX, channel_id="c", amount_cents=1)
    assert got["ok"] is False and got["error"] == "deposit_registry_unavailable"


def test_a_refused_claim_takes_nothing(monkeypatch, one_node):
    """The second claimant must not leave half its names behind: a later, legitimate claim
    of ANOTHER transaction under those names must not collide, and a release by the first
    claimant frees the transaction entirely."""
    assert channels._claim_deposit_shared(chain="base", tx_hash=TX, channel_id="c1", amount_cents=1)["ok"]
    assert not channels._claim_deposit_shared(chain="ethereum", tx_hash=TX, channel_id="c2", amount_cents=1)["ok"]
    channels._release_deposit_shared(chain="base", tx_hash=TX, channel_id="c1")
    assert channels._claim_deposit_shared(chain="ethereum", tx_hash=TX, channel_id="c3", amount_cents=1)["ok"]
