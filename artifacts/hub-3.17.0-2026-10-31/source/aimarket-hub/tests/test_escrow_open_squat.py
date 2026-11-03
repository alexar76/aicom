"""An escrow channel id is public, so an unproven ledger open must not lock its depositor out.

The squatter cannot spend (every debit needs the depositor's EIP-712 signature), but the
ledger refused a second open on the same escrow channel: the real depositor was blocked.
A payer proof from the depositor's wallet now takes an unused, unproven channel back.
"""

from __future__ import annotations

import pytest

from aimarket_hub import channels

DEPOSITOR = "0x6E94c380d908531f9822035d6cc4c8D2B0186C9c"
ESCROW = "0x" + "e1" * 32


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    led = channels.ChannelLedger(db_path=str(tmp_path / "squat.db"))
    monkeypatch.setattr(led, "_verify_escrow_funding",
                        lambda **kw: (True, "", "escrow:" + kw["escrow_channel_id"]))
    monkeypatch.setattr(channels, "_recover_payer_address",
                        lambda **kw: DEPOSITOR if kw.get("signature") == "good" else None)
    return led


def test_an_unproven_open_no_longer_locks_the_depositor_out(ledger):
    squat = ledger.open(deposit_usd=5.0, wallet=DEPOSITOR, escrow_channel_id=ESCROW)
    assert "channel" in squat
    blocked = ledger.open(deposit_usd=5.0, wallet=DEPOSITOR, escrow_channel_id=ESCROW)
    assert "error" in blocked                         # without proof: still refused
    mine = ledger.open(deposit_usd=5.0, wallet=DEPOSITOR, escrow_channel_id=ESCROW,
                       payer_signature="good")
    assert "channel" in mine
    assert mine["channel"]["channel_id"] != squat["channel"]["channel_id"]


def test_a_bad_proof_takes_nothing_back(ledger):
    ledger.open(deposit_usd=5.0, wallet=DEPOSITOR, escrow_channel_id=ESCROW)
    out = ledger.open(deposit_usd=5.0, wallet=DEPOSITOR, escrow_channel_id=ESCROW, payer_signature="bad")
    assert "error" in out and "challenge" in out


def test_a_proven_channel_is_never_superseded(ledger):
    first = ledger.open(deposit_usd=5.0, wallet=DEPOSITOR, escrow_channel_id=ESCROW, payer_signature="good")
    assert "channel" in first
    again = ledger.open(deposit_usd=5.0, wallet=DEPOSITOR, escrow_channel_id=ESCROW, payer_signature="good")
    assert "error" in again
