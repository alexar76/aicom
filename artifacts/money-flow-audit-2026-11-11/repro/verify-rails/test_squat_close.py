import sys
sys.path.insert(0, "/Users/alex/Desktop/ai_tests/aicompany/aicom/.claude/worktrees/bold-volhard-8c154f/aimarket-hub")
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


def test_squat_then_close_locks_depositor_out(ledger):
    # attacker: no proof, names the (public) depositor address read from the chain
    squat = ledger.open(deposit_usd=5.0, wallet=DEPOSITOR, escrow_channel_id=ESCROW)
    assert "channel" in squat
    sq = squat["channel"]
    closed = ledger.close(sq["channel_id"], wallet=DEPOSITOR, secret=sq["channel_secret"])
    print("attacker close:", closed)
    assert "settlement" in closed
    # depositor with a valid proof
    mine = ledger.open(deposit_usd=5.0, wallet=DEPOSITOR, escrow_channel_id=ESCROW, payer_signature="good")
    print("depositor proven open:", mine)
    assert "error" in mine


def test_proven_channel_cannot_be_reopened_after_ledger_expiry(ledger):
    first = ledger.open(deposit_usd=5.0, wallet=DEPOSITOR, escrow_channel_id=ESCROW, payer_signature="good")
    cid = first["channel"]["channel_id"]
    with ledger._get_conn() as conn:
        conn.execute("UPDATE channels SET expires_at = '2000-01-01T00:00:00Z' WHERE channel_id = ?", (cid,))
        conn.commit()
    assert ledger._sweep_expired() == 1
    again = ledger.open(deposit_usd=4.0, wallet=DEPOSITOR, escrow_channel_id=ESCROW, payer_signature="good")
    print("reopen after ledger expiry:", again)
    assert "error" in again
