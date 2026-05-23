"""Comprehensive tests for payment channels — SQLite persistence, integer cents, replay protection, rate limiting, sweep."""

import os
import sqlite3
import tempfile
import time

import pytest

from aimarket_hub.channels import (
    ChannelLedger,
    _cents_to_dollars,
    _dollars_to_cents,
    close_channel,
    debit_channel,
    open_channel,
    refund_channel,
    channel_stats,
)


# ── Helpers ──────────────────────────────────────────────────────

@pytest.fixture
def tmp_db():
    """Create a temporary SQLite database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="test_channels_")
    os.close(fd)
    yield path
    for ext in ("", "-wal", "-shm"):
        try:
            os.remove(path + ext)
        except OSError:
            pass


@pytest.fixture
def ledger(tmp_db):
    """Create a ledger with temporary DB, auto-cleanup."""
    l = ChannelLedger(db_path=tmp_db)
    l._MAX_CHANNELS = 10_000  # Don't limit tests
    yield l
    l.stop_sweep()


# ── Integer Cents Conversion ─────────────────────────────────────

class TestCentsConversion:
    def test_dollars_to_cents(self):
        assert _dollars_to_cents(1.00) == 100
        assert _dollars_to_cents(0.10) == 10
        assert _dollars_to_cents(0.01) == 1
        assert _dollars_to_cents(5.99) == 599

    def test_cents_to_dollars(self):
        assert _cents_to_dollars(100) == 1.00
        assert _cents_to_dollars(10) == 0.10
        assert _cents_to_dollars(1) == 0.01

    def test_roundtrip(self):
        for usd in (0.01, 0.10, 0.99, 1.00, 5.50, 100.00, 9999.99):
            assert _cents_to_dollars(_dollars_to_cents(usd)) == usd


# ── Channel Open ─────────────────────────────────────────────────

class TestChannelOpen:
    def test_happy_path(self, ledger):
        r = ledger.open(deposit_usd=5.0, wallet="0xAlice")
        assert "error" not in r, r
        ch = r["channel"]
        assert ch["balance_usd"] == 5.0
        assert ch["status"] == "open"
        assert ch["channel_id"].startswith("ch_")
        assert ch["wallet"] == "0xAlice"

    def test_invalid_negative(self, ledger):
        assert "error" in ledger.open(-1.0)

    def test_invalid_zero(self, ledger):
        assert "error" in ledger.open(0)

    def test_invalid_over_max(self, ledger):
        assert "error" in ledger.open(20_000.0)

    def test_at_max_allowed(self, ledger):
        r = ledger.open(10_000.0)
        assert "channel" in r, f"Should allow ${10_000}: {r}"

    def test_default_token_chain(self, ledger):
        r = ledger.open(5.0)
        ch = r["channel"]
        assert ch["token"] == "USDT"
        assert ch["chain"] == "base"

    def test_custom_token_chain(self, ledger):
        r = ledger.open(5.0, token="USDC", chain="ethereum")
        ch = r["channel"]
        assert ch["token"] == "USDC"
        assert ch["chain"] == "ethereum"

    def test_expiry_set(self, ledger):
        r = ledger.open(5.0)
        assert r["channel"]["expires_at"] > r["channel"]["opened_at"]

    def test_recipient_recorded(self, ledger):
        r = ledger.open(5.0)
        assert "recipient" in r["channel"]


# ── Channel Close ────────────────────────────────────────────────

class TestChannelClose:
    def test_happy_path(self, ledger):
        r = ledger.open(5.0, wallet="0xAlice")
        cid = r["channel"]["channel_id"]
        s = ledger.close(cid, wallet="0xAlice")["settlement"]
        assert s["refund_usd"] == 5.0
        assert s["status"] == "settled"

    def test_not_found(self, ledger):
        assert "error" in ledger.close("ch_nonexistent")

    def test_already_closed(self, ledger):
        r = ledger.open(1.0)
        cid = r["channel"]["channel_id"]
        ledger.close(cid)
        assert "error" in ledger.close(cid)

    def test_unauthorized_wallet(self, ledger):
        r = ledger.open(5.0, wallet="0xAlice")
        cid = r["channel"]["channel_id"]
        assert "error" in ledger.close(cid, wallet="0xEve")

    def test_anonymous_close_any(self, ledger):
        """Channels require wallet match — anonymous channels can only be closed by their owner."""
        r = ledger.open(5.0, wallet="")
        cid = r["channel"]["channel_id"]
        # Different wallet should be rejected
        result = ledger.close(cid, wallet="0xAnyone")
        assert "error" in result
        # Same empty wallet should work
        s = ledger.close(cid, wallet="")["settlement"]
        assert s["status"] == "settled"

    def test_settle_tx_hash(self, ledger):
        r = ledger.open(5.0)
        cid = r["channel"]["channel_id"]
        s = ledger.close(cid, settle_tx_hash="0xdeadbeef")["settlement"]
        assert s["settle_tx_hash"] == "0xdeadbeef"


# ── Channel Debit ────────────────────────────────────────────────

class TestChannelDebit:
    def test_happy_path(self, ledger):
        r = ledger.open(5.0)
        cid = r["channel"]["channel_id"]
        d = ledger.debit(cid, 2.0)
        assert d["ok"] is True
        assert abs(d["remaining_balance"] - 3.0) < 0.01

    def test_not_found(self, ledger):
        assert "error" in ledger.debit("ch_nonexistent", 1.0)

    def test_not_open(self, ledger):
        r = ledger.open(1.0)
        cid = r["channel"]["channel_id"]
        ledger.close(cid)
        assert "error" in ledger.debit(cid, 0.5)

    def test_insufficient(self, ledger):
        r = ledger.open(1.0)
        cid = r["channel"]["channel_id"]
        d = ledger.debit(cid, 50.0)
        assert "error" in d
        assert "insufficient" in d["error"]

    def test_replay_protection(self, ledger):
        r = ledger.open(5.0)
        cid = r["channel"]["channel_id"]
        ledger.debit(cid, 0.10, receipt_id="rcpt_A")
        d = ledger.debit(cid, 0.10, receipt_id="rcpt_A")
        assert "error" in d
        assert "replay" in d["error"]

    def test_different_receipts_ok(self, ledger):
        r = ledger.open(5.0)
        cid = r["channel"]["channel_id"]
        assert ledger.debit(cid, 0.10, receipt_id="rcpt_1")["ok"]
        assert ledger.debit(cid, 0.10, receipt_id="rcpt_2")["ok"]

    def test_multiple_debits(self, ledger):
        r = ledger.open(5.0)
        cid = r["channel"]["channel_id"]
        for i in range(10):
            assert ledger.debit(cid, 0.10, receipt_id=f"rcpt_{i}")["ok"]
        assert abs(ledger.get(cid)["balance_usd"] - 4.0) < 0.01
        assert abs(ledger.get(cid)["used_usd"] - 1.0) < 0.01

    def test_small_amount(self, ledger):
        r = ledger.open(1.0)
        cid = r["channel"]["channel_id"]
        d = ledger.debit(cid, 0.01)
        assert d["ok"] is True
        assert abs(d["remaining_balance"] - 0.99) < 0.01


# ── Channel Refund ───────────────────────────────────────────────

class TestChannelRefund:
    def test_partial_refund(self, ledger):
        r = ledger.open(5.0)
        cid = r["channel"]["channel_id"]
        ledger.debit(cid, 3.0)
        d = ledger.refund(cid, 1.0)
        assert d["ok"] is True
        assert abs(d["remaining_balance"] - 3.0) < 0.01  # 5-3+1

    def test_full_refund_after_debit(self, ledger):
        r = ledger.open(5.0)
        cid = r["channel"]["channel_id"]
        ledger.debit(cid, 3.0)
        ledger.refund(cid, 3.0)
        assert abs(ledger.get(cid)["balance_usd"] - 5.0) < 0.01

    def test_refund_unknown(self, ledger):
        assert "error" in ledger.refund("ch_nonexistent", 1.0)


# ── SQLite Persistence ────────────────────────────────────────────

class TestPersistence:
    def test_channel_survives_restart(self, tmp_db):
        l1 = ChannelLedger(db_path=tmp_db)
        r = l1.open(10.0, wallet="0xAlice")
        cid = r["channel"]["channel_id"]
        l1.debit(cid, 3.50, receipt_id="rcpt_persist")
        l1.stop_sweep()

        # Re-open ledger
        l2 = ChannelLedger(db_path=tmp_db)
        ch = l2.get(cid)
        assert ch is not None, "Channel lost after restart!"
        assert ch["status"] == "open"
        assert abs(ch["balance_usd"] - 6.50) < 0.01
        assert abs(ch["used_usd"] - 3.50) < 0.01
        l2.stop_sweep()

    def test_receipt_survives_restart(self, tmp_db):
        l1 = ChannelLedger(db_path=tmp_db)
        r = l1.open(5.0)
        cid = r["channel"]["channel_id"]
        l1.debit(cid, 0.10, receipt_id="rcpt_survive")
        l1.stop_sweep()

        l2 = ChannelLedger(db_path=tmp_db)
        d = l2.debit(cid, 0.10, receipt_id="rcpt_survive")
        assert "error" in d, "Replay should be caught after restart"
        assert "replay" in d["error"]
        l2.stop_sweep()

    def test_settled_status_persists(self, tmp_db):
        l1 = ChannelLedger(db_path=tmp_db)
        r = l1.open(5.0, wallet="0xAlice")
        cid = r["channel"]["channel_id"]
        l1.close(cid, wallet="0xAlice")
        l1.stop_sweep()

        l2 = ChannelLedger(db_path=tmp_db)
        assert l2.get(cid)["status"] == "settled"
        l2.stop_sweep()


# ── Rate Limiting ────────────────────────────────────────────────

class TestRateLimiting:
    def test_open_rate_limit(self, ledger):
        ledger._rate_state.clear()
        wallet = "0xRateLimitOpen"
        for i in range(20):
            r = ledger.open(0.10, wallet=wallet)
            assert "channel" in r, f"Open {i + 1} should succeed: {r.get('error', '')}"
        # 21st should fail
        r = ledger.open(0.10, wallet=wallet)
        assert "error" in r, f"Open 21 should be rate-limited"
        assert "rate limit" in r["error"]

    def test_close_rate_limit(self, ledger):
        ledger._close_rate.clear()
        shared_wallet = "0xSharedCloser"
        cids = []

        # Open 61 channels — clear rate between each to avoid open rate limit
        for i in range(61):
            ledger._rate_state.pop(shared_wallet, None)
            r = ledger.open(0.10, wallet=shared_wallet)
            cids.append(r["channel"]["channel_id"])

        # Clear rate state again so close rate limit test is clean
        ledger._close_rate.clear()

        # Close 60 — all within limit
        for i in range(60):
            s = ledger.close(cids[i], wallet=shared_wallet)
            assert "error" not in s, f"Close {i} should succeed: {s.get('error', '')}"
        # 61st close with same wallet should be rate-limited
        r = ledger.close(cids[60], wallet=shared_wallet)
        assert "error" in r, f"Close 61 should be rate-limited: {r}"

    def test_different_wallets_independent(self, ledger):
        ledger._rate_state.clear()
        # Alice uses all her limit
        for i in range(20):
            ledger.open(0.10, wallet="0xAlice")
        assert "error" in ledger.open(0.10, wallet="0xAlice")
        # Bob can still open
        assert "channel" in ledger.open(5.0, wallet="0xBob")


# ── DoS Protection ───────────────────────────────────────────────

class TestDosProtection:
    def test_max_channels(self, tmp_db):
        """Test DoS cap with a dedicated ledger instance."""
        import os, uuid
        l = ChannelLedger(db_path=tmp_db)
        l.stop_sweep()
        l._max_channels = 2
        assert "channel" in l.open(0.10, wallet="0xA")
        assert "channel" in l.open(0.10, wallet="0xB")
        r = l.open(0.10, wallet="0xC")
        assert "error" in r, f"Should block at max=2: {r}"
        assert "too many" in r["error"]


# ── Edge Cases ───────────────────────────────────────────────────

class TestEdgeCases:
    def test_fractional_cent_rounding(self, ledger):
        """1/3 = 0.333... should round cleanly."""
        r = ledger.open(1.00)
        cid = r["channel"]["channel_id"]
        d = ledger.debit(cid, 0.33)
        assert d["ok"] is True

    def test_many_small_debits(self, ledger):
        """100 debits of $0.01 should not drift."""
        r = ledger.open(5.00)
        cid = r["channel"]["channel_id"]
        for i in range(100):
            ledger.debit(cid, 0.01, receipt_id=f"micro_{i}")
        ch = ledger.get(cid)
        assert abs(ch["balance_usd"] - 4.00) < 0.001, f"Float drift: {ch['balance_usd']} != 4.00"

    def test_channel_id_entropy(self, ledger):
        ids = set()
        for i in range(100):
            cid = ledger.open(0.10)["channel"]["channel_id"]
            ids.add(cid)
        assert len(ids) == 100, f"Collision: {len(ids)} unique out of 100"


# ── Integration ─────────────────────────────────────────────────

class TestIntegration:
    def test_full_buy_flow(self, ledger):
        r = ledger.open(20.00, wallet="0xBuyer")
        cid = r["channel"]["channel_id"]

        # Buy 5 capabilities
        ledger.debit(cid, 2.00, receipt_id="inv_1")
        ledger.debit(cid, 3.50, receipt_id="inv_2")
        ledger.debit(cid, 0.50, receipt_id="inv_3")
        ledger.debit(cid, 1.00, receipt_id="inv_4")
        ledger.debit(cid, 4.00, receipt_id="inv_5")

        s = ledger.close(cid, wallet="0xBuyer")["settlement"]
        assert abs(s["used_usd"] - 11.00) < 0.01
        assert abs(s["refund_usd"] - 9.00) < 0.01

    def test_safety_refund_flow(self, ledger):
        r = ledger.open(10.00, wallet="0xBuyer")
        cid = r["channel"]["channel_id"]
        ledger.debit(cid, 1.50, receipt_id="inv_good")
        # Safety blocked — refund
        ledger.refund(cid, 1.50)
        s = ledger.close(cid, wallet="0xBuyer")["settlement"]
        assert abs(s["used_usd"] - 0.00) < 0.01
        assert abs(s["refund_usd"] - 10.00) < 0.01

    def test_stats(self, ledger):
        ledger.open(5.0, wallet="0xA")
        ledger.open(3.0, wallet="0xB")
        r = ledger.open(2.0, wallet="0xC")
        ledger.close(r["channel"]["channel_id"], wallet="0xC")

        s = ledger.stats()
        assert s["open_channels"] == 2
        assert s["settled_channels"] == 1


# ── Module-Level Functions ───────────────────────────────────────

class TestModuleFunctions:
    """Tests using the global module-level _ledger singleton."""

    def test_open_close_roundtrip(self):
        r = open_channel(3.00, wallet="0xModTest1")
        assert "channel" in r, r
        cid = r["channel"]["channel_id"]
        s = close_channel(cid, wallet="0xModTest1")["settlement"]
        assert s["refund_usd"] == 3.00

    def test_debit_refund_chain(self):
        import uuid
        tag = uuid.uuid4().hex[:6]
        wallet = f"0xModTest_{tag}"
        r = open_channel(10.00, wallet=wallet)
        assert "channel" in r, r
        cid = r["channel"]["channel_id"]
        debit_channel(cid, 3.00, receipt_id=f"mod_deb_{tag}")
        refund_channel(cid, 1.00)
        s = close_channel(cid, wallet=wallet)["settlement"]
        assert abs(s["used_usd"] - 2.00) < 0.01
        assert abs(s["refund_usd"] - 8.00) < 0.01

    def test_channel_stats(self):
        s = channel_stats()
        assert "open_channels" in s
        assert "settled_channels" in s
