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
    channel_obligations,
    channel_obligations_total,
    channel_stats,
    close_channel,
    debit_channel,
    open_channel,
    refund_channel,
)

import itertools as _itertools

_RIDS = _itertools.count()


def _rid() -> str:
    """A fresh receipt id: a debit that moves money must name the operation it pays for."""
    return f"test-receipt-{next(_RIDS)}"



@pytest.fixture(autouse=True)
def _crypto_enabled(monkeypatch):
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")


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
        assert ch["token"] == "USDC"  # default payment token switched to real USDC on Base
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
        s = ledger.close(cid, wallet="0xAlice", secret=r["channel"]["channel_secret"])["settlement"]
        assert s["refund_usd"] == 5.0
        assert s["status"] == "settled"

    def test_not_found(self, ledger):
        assert "error" in ledger.close("ch_nonexistent")

    def test_already_closed(self, ledger):
        r = ledger.open(1.0)
        cid = r["channel"]["channel_id"]
        ledger.close(cid, secret=r["channel"]["channel_secret"])
        assert "error" in ledger.close(cid, secret=r["channel"]["channel_secret"])

    def test_unauthorized_wallet(self, ledger):
        r = ledger.open(5.0, wallet="0xAlice")
        cid = r["channel"]["channel_id"]
        assert "error" in ledger.close(cid, wallet="0xEve", secret=r["channel"]["channel_secret"])

    def test_anonymous_close_requires_secret_and_empty_wallet(self, ledger):
        """An anonymous channel still requires its secret, alongside the empty wallet."""
        r = ledger.open(5.0, wallet="")
        cid = r["channel"]["channel_id"]
        # Different wallet should be rejected
        result = ledger.close(cid, wallet="0xAnyone", secret=r["channel"]["channel_secret"])
        assert "error" in result
        # The matching secret and empty wallet should work
        s = ledger.close(cid, wallet="", secret=r["channel"]["channel_secret"])["settlement"]
        assert s["status"] == "settled"

    def test_settle_tx_hash(self, ledger):
        r = ledger.open(5.0)
        cid = r["channel"]["channel_id"]
        s = ledger.close(cid, settle_tx_hash="0xdeadbeef", secret=r["channel"]["channel_secret"])["settlement"]
        assert s["settle_tx_hash"] == "0xdeadbeef"


# ── Channel Debit ────────────────────────────────────────────────

class TestChannelDebit:
    def test_happy_path(self, ledger):
        r = ledger.open(5.0)
        cid = r["channel"]["channel_id"]
        d = ledger.debit(cid, 2.0, secret=r["channel"]["channel_secret"], receipt_id=_rid())
        assert d["ok"] is True
        assert abs(d["remaining_balance"] - 3.0) < 0.01

    def test_not_found(self, ledger):
        assert "error" in ledger.debit("ch_nonexistent", 1.0, receipt_id=_rid())

    def test_not_open(self, ledger):
        r = ledger.open(1.0)
        cid = r["channel"]["channel_id"]
        ledger.close(cid, secret=r["channel"]["channel_secret"])
        assert "error" in ledger.debit(cid, 0.5, secret=r["channel"]["channel_secret"], receipt_id=_rid())

    def test_insufficient(self, ledger):
        r = ledger.open(1.0)
        cid = r["channel"]["channel_id"]
        d = ledger.debit(cid, 50.0, secret=r["channel"]["channel_secret"], receipt_id=_rid())
        assert "error" in d
        assert "insufficient" in d["error"]

    def test_replay_protection(self, ledger):
        r = ledger.open(5.0)
        cid = r["channel"]["channel_id"]
        ledger.debit(cid, 0.10, receipt_id="rcpt_A", secret=r["channel"]["channel_secret"])
        d = ledger.debit(cid, 0.10, receipt_id="rcpt_A", secret=r["channel"]["channel_secret"])
        assert "error" in d
        assert "replay" in d["error"]

    def test_different_receipts_ok(self, ledger):
        r = ledger.open(5.0)
        cid = r["channel"]["channel_id"]
        assert ledger.debit(cid, 0.10, receipt_id="rcpt_1", secret=r["channel"]["channel_secret"])["ok"]
        assert ledger.debit(cid, 0.10, receipt_id="rcpt_2", secret=r["channel"]["channel_secret"])["ok"]

    def test_multiple_debits(self, ledger):
        r = ledger.open(5.0)
        cid = r["channel"]["channel_id"]
        for i in range(10):
            assert ledger.debit(cid, 0.10, receipt_id=f"rcpt_{i}", secret=r["channel"]["channel_secret"])["ok"]
        assert abs(ledger.get(cid)["balance_usd"] - 4.0) < 0.01
        assert abs(ledger.get(cid)["used_usd"] - 1.0) < 0.01

    def test_small_amount(self, ledger):
        r = ledger.open(1.0)
        cid = r["channel"]["channel_id"]
        d = ledger.debit(cid, 0.01, secret=r["channel"]["channel_secret"], receipt_id=_rid())
        assert d["ok"] is True
        assert abs(d["remaining_balance"] - 0.99) < 0.01


# ── Channel Refund ───────────────────────────────────────────────

class TestChannelRefund:
    def test_partial_refund(self, ledger):
        r = ledger.open(5.0)
        cid = r["channel"]["channel_id"]
        ledger.debit(cid, 3.0, secret=r["channel"]["channel_secret"], receipt_id=_rid())
        d = ledger.refund(cid, 1.0, secret=r["channel"]["channel_secret"])
        assert d["ok"] is True
        assert abs(d["remaining_balance"] - 3.0) < 0.01  # 5-3+1

    def test_full_refund_after_debit(self, ledger):
        r = ledger.open(5.0)
        cid = r["channel"]["channel_id"]
        ledger.debit(cid, 3.0, secret=r["channel"]["channel_secret"], receipt_id=_rid())
        ledger.refund(cid, 3.0, secret=r["channel"]["channel_secret"])
        assert abs(ledger.get(cid)["balance_usd"] - 5.0) < 0.01

    def test_refund_unknown(self, ledger):
        assert "error" in ledger.refund("ch_nonexistent", 1.0)


# ── SQLite Persistence ────────────────────────────────────────────

class TestPersistence:
    def test_channel_survives_restart(self, tmp_db):
        l1 = ChannelLedger(db_path=tmp_db)
        r = l1.open(10.0, wallet="0xAlice")
        cid = r["channel"]["channel_id"]
        l1.debit(cid, 3.50, receipt_id="rcpt_persist", secret=r["channel"]["channel_secret"])
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
        l1.debit(cid, 0.10, receipt_id="rcpt_survive", secret=r["channel"]["channel_secret"])
        l1.stop_sweep()

        l2 = ChannelLedger(db_path=tmp_db)
        d = l2.debit(cid, 0.10, receipt_id="rcpt_survive", secret=r["channel"]["channel_secret"])
        assert "error" in d, "Replay should be caught after restart"
        assert "replay" in d["error"]
        l2.stop_sweep()

    def test_settled_status_persists(self, tmp_db):
        l1 = ChannelLedger(db_path=tmp_db)
        r = l1.open(5.0, wallet="0xAlice")
        cid = r["channel"]["channel_id"]
        l1.close(cid, wallet="0xAlice", secret=r["channel"]["channel_secret"])
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
        assert "error" in r, "Open 21 should be rate-limited"
        assert "rate limit" in r["error"]

    def test_close_rate_limit(self, ledger):
        ledger._close_rate.clear()
        shared_wallet = "0xSharedCloser"
        cids = []
        secrets = []

        # Open 61 channels — clear rate between each to avoid open rate limit
        for i in range(61):
            ledger._rate_state.pop(shared_wallet, None)
            r = ledger.open(0.10, wallet=shared_wallet)
            cids.append(r["channel"]["channel_id"])
            secrets.append(r["channel"]["channel_secret"])

        # Clear rate state again so close rate limit test is clean
        ledger._close_rate.clear()

        # Close 60 — all within limit
        for i in range(60):
            s = ledger.close(cids[i], wallet=shared_wallet, secret=secrets[i])
            assert "error" not in s, f"Close {i} should succeed: {s.get('error', '')}"
        # 61st close with same wallet should be rate-limited
        r = ledger.close(cids[60], wallet=shared_wallet, secret=secrets[60])
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
        d = ledger.debit(cid, 0.33, secret=r["channel"]["channel_secret"], receipt_id=_rid())
        assert d["ok"] is True

    def test_many_small_debits(self, ledger):
        """100 debits of $0.01 should not drift."""
        r = ledger.open(5.00)
        cid = r["channel"]["channel_id"]
        for i in range(100):
            ledger.debit(cid, 0.01, receipt_id=f"micro_{i}", secret=r["channel"]["channel_secret"])
        ch = ledger.get(cid)
        assert abs(ch["balance_usd"] - 4.00) < 0.001, f"Float drift: {ch['balance_usd']} != 4.00"

    def test_channel_id_entropy(self, ledger):
        ids = set()
        for i in range(100):
            opened = ledger.open(0.10)["channel"]
            cid = opened["channel_id"]
            ids.add(cid)
        assert len(ids) == 100, f"Collision: {len(ids)} unique out of 100"


# ── Integration ─────────────────────────────────────────────────

class TestIntegration:
    def test_full_buy_flow(self, ledger):
        r = ledger.open(20.00, wallet="0xBuyer")
        cid = r["channel"]["channel_id"]

        # Buy 5 capabilities
        ledger.debit(cid, 2.00, receipt_id="inv_1", secret=r["channel"]["channel_secret"])
        ledger.debit(cid, 3.50, receipt_id="inv_2", secret=r["channel"]["channel_secret"])
        ledger.debit(cid, 0.50, receipt_id="inv_3", secret=r["channel"]["channel_secret"])
        ledger.debit(cid, 1.00, receipt_id="inv_4", secret=r["channel"]["channel_secret"])
        ledger.debit(cid, 4.00, receipt_id="inv_5", secret=r["channel"]["channel_secret"])

        s = ledger.close(cid, wallet="0xBuyer", secret=r["channel"]["channel_secret"])["settlement"]
        assert abs(s["used_usd"] - 11.00) < 0.01
        assert abs(s["refund_usd"] - 9.00) < 0.01

    def test_safety_refund_flow(self, ledger):
        r = ledger.open(10.00, wallet="0xBuyer")
        cid = r["channel"]["channel_id"]
        ledger.debit(cid, 1.50, receipt_id="inv_good", secret=r["channel"]["channel_secret"])
        # Safety blocked — refund
        ledger.refund(cid, 1.50, secret=r["channel"]["channel_secret"])
        s = ledger.close(cid, wallet="0xBuyer", secret=r["channel"]["channel_secret"])["settlement"]
        assert abs(s["used_usd"] - 0.00) < 0.01
        assert abs(s["refund_usd"] - 10.00) < 0.01

    def test_stats(self, ledger):
        ledger.open(5.0, wallet="0xA")
        ledger.open(3.0, wallet="0xB")
        r = ledger.open(2.0, wallet="0xC")
        ledger.close(r["channel"]["channel_id"], wallet="0xC", secret=r["channel"]["channel_secret"])

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
        sec = r["channel"]["channel_secret"]
        s = close_channel(cid, wallet="0xModTest1", secret=sec)["settlement"]
        assert s["refund_usd"] == 3.00

    def test_close_requires_the_channel_secret_not_just_the_wallet(self):
        """A wallet address is public; possession of the debit secret is not.

        /stats/live labelled paid invokes `channel:<id>` and deposit payers are on-chain,
        so "present the depositor's address" let a stranger force the channel closed and
        strand the remainder as an obligation. close() now authorizes like debit()/hold().
        """
        r = open_channel(2.00, wallet="0xCloseAuth1")
        cid = r["channel"]["channel_id"]
        sec = r["channel"]["channel_secret"]
        assert sec, "open_channel should mint a debit secret by default"

        stranger = close_channel(cid, wallet="0xCloseAuth1")   # correct wallet, no secret
        assert "unauthorized" in stranger.get("error", "")
        wrong = close_channel(cid, wallet="0xCloseAuth1", secret="not-the-secret")
        assert "unauthorized" in wrong.get("error", "")

        owner = close_channel(cid, wallet="0xCloseAuth1", secret=sec)
        assert owner.get("settlement", {}).get("refund_usd") == 2.00

    def test_debit_refund_chain(self):
        import uuid
        tag = uuid.uuid4().hex[:6]
        wallet = f"0xModTest_{tag}"
        r = open_channel(10.00, wallet=wallet)
        assert "channel" in r, r
        cid = r["channel"]["channel_id"]
        sec = r["channel"]["channel_secret"]  # open_channel mints a debit secret (secure default)
        debit_channel(cid, 3.00, receipt_id=f"mod_deb_{tag}", secret=sec)
        # refund now carries the same authorization as debit
        assert refund_channel(cid, 1.00, secret=sec).get("ok")
        s = close_channel(cid, wallet=wallet, secret=sec)["settlement"]
        assert abs(s["used_usd"] - 2.00) < 0.01
        assert abs(s["refund_usd"] - 8.00) < 0.01

    def test_channel_stats(self):
        s = channel_stats()
        assert "open_channels" in s
        assert "settled_channels" in s


class TestDebitAuthorization:
    """SEC: debit() must honour channel-owner wallet when the caller identity is known."""

    def test_debit_rejects_wrong_requester_wallet(self, ledger):
        # A valid secret does not bypass the additional wallet ownership check.
        opened = ledger.open(5.0, wallet="0xAlice")["channel"]
        cid = opened["channel_id"]
        assert "error" in ledger.debit(cid, 1.0, requester_wallet="0xMallory", secret=opened["channel_secret"], receipt_id=_rid())
        assert ledger.debit(cid, 1.0, requester_wallet="0xAlice", secret=opened["channel_secret"], receipt_id=_rid()).get("ok")   # owner
        assert ledger.debit(cid, 1.0, secret=opened["channel_secret"], receipt_id=_rid()).get("ok")                                # secret authenticates without a wallet claim


class TestDebitSecret:
    """SEC (PAYAUTH): a channel opened with a debit secret REQUIRES it — a leaked channel id
    alone can't drain it. Both public and low-level opens mint a secret by default."""

    def test_secret_required_and_verified(self, ledger):
        r = ledger.open(5.0, wallet="0xAlice", with_secret=True)["channel"]
        cid, sec = r["channel_id"], r["channel_secret"]
        assert sec  # returned once
        assert "error" in ledger.debit(cid, 1.0, receipt_id=_rid())                       # missing secret
        assert "error" in ledger.debit(cid, 1.0, secret="wrong", receipt_id=_rid())       # wrong secret
        assert ledger.debit(cid, 1.0, secret=sec, receipt_id=_rid()).get("ok")           # correct secret

    def test_open_channel_wrapper_is_secure_by_default(self):
        r = open_channel(2.0, wallet="0xBob")["channel"]
        assert r.get("channel_secret")  # the HTTP/production entry point always mints a secret

    def test_explicit_secretless_channel_cannot_debit(self, ledger):
        cid = ledger.open(5.0, wallet="0xCarol", with_secret=False)["channel"]["channel_id"]
        assert ledger.debit(cid, 1.0, receipt_id=_rid())["error"].startswith("unauthorized:")


class TestDemoCreditFailClosed:
    """SEC: unverified deposits must NOT credit a channel unless prod (verify) or explicit demo."""

    def test_open_rejected_without_prod_or_demo_flag(self, ledger, monkeypatch):
        monkeypatch.delenv("AIMARKET_ALLOW_DEMO_CREDIT", raising=False)
        monkeypatch.delenv("AIFACTORY_PROD", raising=False)
        r = ledger.open(5.0, wallet="0xAlice")
        assert "error" in r and "verification" in r["error"]

    def test_open_allowed_with_demo_flag(self, ledger, monkeypatch):
        monkeypatch.setenv("AIMARKET_ALLOW_DEMO_CREDIT", "1")
        assert "channel" in ledger.open(5.0, wallet="0xAlice")


class TestDepositSingleUse:
    """SEC (PAYAUTH-002): a verified on-chain deposit may fund exactly ONE channel.

    Without the consumed_deposits guard, one real USDC deposit could be replayed to
    POST /channel/open unlimited times, each minting a full spendable balance.
    """

    @pytest.fixture
    def prod_ledger(self, tmp_db, monkeypatch):
        import aimarket_hub.channels as ch
        _prod_mode(monkeypatch, ch, sender=_EVM_PAYER)
        l = ch.ChannelLedger(db_path=tmp_db)
        yield l
        l.stop_sweep()

    def test_same_tx_hash_funds_only_one_channel(self, prod_ledger):
        first = prod_ledger.open(5.0, tx_hash="0xdeposit1", **_PROOF)
        assert "channel" in first, first
        replay = prod_ledger.open(5.0, tx_hash="0xdeposit1", **_PROOF)
        assert "error" in replay, f"deposit replay must be rejected: {replay}"
        assert "already used" in replay["error"]

    def test_distinct_tx_hashes_each_fund_a_channel(self, prod_ledger):
        assert "channel" in prod_ledger.open(5.0, tx_hash="0xdepA", **_PROOF)
        assert "channel" in prod_ledger.open(5.0, tx_hash="0xdepB", **_PROOF)

    def test_case_variant_tx_hash_is_the_same_deposit(self, prod_ledger):
        """PAYAUTH-002: an EVM tx hash is case-insensitive at the RPC layer.

        Claiming it verbatim let ONE real deposit mint a fully funded channel per
        capitalisation (0xDEADBEEF, 0xdeadbeef, 0xDeadBeef, ...).
        """
        assert "channel" in prod_ledger.open(5.0, tx_hash="0xDEADBEEF", **_PROOF)
        for variant in ("0xdeadbeef", "0xDeadBeef", "0xdeadBEEF"):
            replay = prod_ledger.open(5.0, tx_hash=variant, **_PROOF)
            assert "error" in replay, f"{variant} re-funded the same deposit: {replay}"
            assert "already used" in replay["error"]
        assert prod_ledger.stats()["open_channels"] == 1

    def test_case_variant_chain_is_the_same_deposit(self, prod_ledger):
        assert "channel" in prod_ledger.open(
            5.0, chain="base", tx_hash="0xfeed01", **_PROOF)
        for variant in ("Base", "BASE", " base "):
            replay = prod_ledger.open(5.0, chain=variant, tx_hash="0xfeed01", **_PROOF)
            assert "error" in replay, f"chain={variant!r} re-funded the deposit: {replay}"
        assert prod_ledger.stats()["open_channels"] == 1

    def test_base58_deposit_id_keeps_its_case(self, tmp_db, monkeypatch):
        """Solana signatures are base58 — case is part of the identifier, so two
        differently-cased ids are genuinely different transactions."""
        import aimarket_hub.channels as ch
        _prod_mode(monkeypatch, ch, sender=_EVM_PAYER)
        led = ch.ChannelLedger(db_path=tmp_db)
        try:
            assert "channel" in led.open(
                1.0, chain="solana", tx_hash="5KtPn1", **_PROOF)
            assert "channel" in led.open(
                1.0, chain="solana", tx_hash="5ktpN1", **_PROOF)
            replay = led.open(1.0, chain="solana", tx_hash="5KtPn1", **_PROOF)
            assert "error" in replay and "already used" in replay["error"]
        finally:
            led.stop_sweep()

    def test_legacy_mixed_case_claim_row_still_blocks_a_replay(self, prod_ledger):
        """Back-compat: rows written before the canonical key are stored in whatever
        case they arrived in — the lookup must still find them."""
        with prod_ledger._get_conn() as conn:
            conn.execute(
                "INSERT INTO consumed_deposits (chain, tx_hash, channel_id, "
                "amount_cents, consumed_at) VALUES ('Base', '0xLEGACY01', 'ch_old', "
                "500, '2026-01-01T00:00:00Z')"
            )
            conn.commit()
        replay = prod_ledger.open(5.0, chain="base", tx_hash="0xlegacy01", **_PROOF)
        assert "error" in replay and "already used" in replay["error"]

    def test_claim_survives_restart(self, tmp_db, monkeypatch):
        import aimarket_hub.channels as ch
        _prod_mode(monkeypatch, ch, sender=_EVM_PAYER)
        l1 = ch.ChannelLedger(db_path=tmp_db)
        assert "channel" in l1.open(5.0, tx_hash="0xpersist", **_PROOF)
        l1.stop_sweep()
        l2 = ch.ChannelLedger(db_path=tmp_db)
        replay = l2.open(5.0, tx_hash="0xpersist", **_PROOF)
        assert "error" in replay and "already used" in replay["error"]
        l2.stop_sweep()


class TestSubCentBilling:
    """BILLING-001: a positively-priced invoke must never debit 0 cents."""

    def test_sub_half_cent_bills_one_cent(self, ledger):
        from aimarket_hub.channels import _dollars_to_cents_bill
        assert _dollars_to_cents_bill(0.004) == 1
        assert _dollars_to_cents_bill(0.011) == 2
        assert _dollars_to_cents_bill(0.35) == 35   # exact cents not pushed up
        assert _dollars_to_cents_bill(0.0) == 0

    def test_sub_cent_debit_charges_minimum(self, ledger):
        opened = ledger.open(1.0)["channel"]
        cid = opened["channel_id"]
        d = ledger.debit(cid, 0.004, secret=opened["channel_secret"], receipt_id=_rid())
        assert d["ok"] is True
        # billed 1 cent rather than executing for free
        assert abs(ledger.get(cid)["used_usd"] - 0.01) < 1e-9


# ── Deposit → payer binding (PAYAUTH-003) ────────────────────────

_EVM_PAYER = "0x" + "Ab" * 20          # EIP-55-style mixed case
_EVM_PAYER_LOWER = _EVM_PAYER.lower()
_EVM_OTHER = "0x" + "cd" * 20

# The only signature the stubbed recovery below accepts.
_GOOD_SIG = "0xgoodproof"
_PROOF = {"wallet": _EVM_PAYER, "payer_signature": _GOOD_SIG}


def _prod_mode(monkeypatch, ch, *, sender=_EVM_PAYER, proof_signer=_EVM_PAYER):
    """Put the channels module on the production (on-chain-verified) path.

    The real proof path needs eth_account (absent from the hub test venv), so
    _recover_payer_address is stubbed: it recovers `proof_signer` for _GOOD_SIG and
    nothing for anything else — exactly the shape of a real ECDSA recovery. The stub
    takes `deposit_usd` because the canonical challenge binds the amount.
    """
    monkeypatch.setattr(ch, "_is_production_mode", lambda: True)
    monkeypatch.setattr(ch, "_VERIFY_STUB", False)
    monkeypatch.setattr(
        ch, "_verify_tx_onchain", lambda **kw: {"ok": True, "sender": sender}
    )
    monkeypatch.setattr(
        ch, "_recover_payer_address",
        lambda *, payer, tx_hash, chain, deposit_usd, signature: (
            proof_signer if signature == _GOOD_SIG else None
        ),
    )


class TestDepositSenderBinding:
    """SEC (PAYAUTH-003): a deposit is credited ONLY to the wallet that paid on-chain.

    Every deposit lands in the same platform settlement wallet, so verifying
    recipient/amount alone lets anyone watching inbound transfers claim a stranger's
    tx hash and have the channel credited to themselves (consumed_deposits stops
    replay, not theft).
    """

    def _ledger(self, tmp_db, monkeypatch, sender=_EVM_PAYER, proof_signer=_EVM_PAYER):
        import aimarket_hub.channels as ch
        _prod_mode(monkeypatch, ch, sender=sender, proof_signer=proof_signer)
        return ch.ChannelLedger(db_path=tmp_db)

    def test_stranger_cannot_claim_someone_elses_deposit(self, tmp_db, monkeypatch):
        led = self._ledger(tmp_db, monkeypatch)
        try:
            r = led.open(5.0, wallet=_EVM_OTHER, tx_hash="0xvictimdeposit",
                         payer_signature=_GOOD_SIG)
            assert "error" in r, r
            assert "does not match" in r["error"]
            # ...and the tx must remain unconsumed, so the real payer can still use it
            ok = led.open(5.0, tx_hash="0xvictimdeposit", **_PROOF)
            assert "channel" in ok, ok
        finally:
            led.stop_sweep()

    def test_payer_binds_case_insensitively_for_evm(self, tmp_db, monkeypatch):
        led = self._ledger(tmp_db, monkeypatch)
        try:
            r = led.open(5.0, wallet=_EVM_PAYER_LOWER, tx_hash="0xdep_case",
                         payer_signature=_GOOD_SIG)
            assert "channel" in r, r
            # stored as the verified on-chain payer
            assert r["channel"]["wallet"] == _EVM_PAYER
            # ...and the lowercase form still authorizes the close
            s = led.close(r["channel"]["channel_id"], wallet=_EVM_PAYER_LOWER, secret=r["channel"]["channel_secret"])
            assert "settlement" in s, s
        finally:
            led.stop_sweep()

    def test_missing_sender_refuses_credit(self, tmp_db, monkeypatch):
        # Verifier confirmed recipient/amount but cannot attribute the payment
        # (e.g. demo-bypass): fail CLOSED rather than credit an unbound deposit.
        led = self._ledger(tmp_db, monkeypatch, sender="")
        try:
            r = led.open(5.0, tx_hash="0xdep_nosender", **_PROOF)
            assert "error" in r, r
            assert "paying wallet" in r["error"]
            assert led.stats()["open_channels"] == 0
        finally:
            led.stop_sweep()

    def test_empty_claimed_wallet_binds_to_payer_not_anonymous(self, tmp_db, monkeypatch):
        # An empty wallet must not be a bypass: the honest rule is that the deposit
        # belongs to whoever paid it.
        led = self._ledger(tmp_db, monkeypatch)
        try:
            r = led.open(5.0, wallet="", tx_hash="0xdep_anon",
                         payer_signature=_GOOD_SIG)
            assert "channel" in r, r
            assert r["channel"]["wallet"] == _EVM_PAYER
            # bound → a wallet-less caller can no longer close it
            assert "error" in led.close(r["channel"]["channel_id"], wallet="", secret=r["channel"]["channel_secret"])
        finally:
            led.stop_sweep()

    def test_verifier_is_the_sender_returning_variant(self, tmp_db, monkeypatch):
        """_verify_tx_onchain must call verify_tx_payment_details, not verify_tx_payment."""
        import sys
        import types

        import aimarket_hub.channels as ch

        calls: list[dict] = []
        mod = types.ModuleType("web.backend.services.ai_market_protocol.on_chain")

        def _details(*, tx_hash, amount_usd, chain, token):
            calls.append({"tx_hash": tx_hash, "amount_usd": amount_usd})
            return True, _EVM_PAYER

        mod.verify_tx_payment_details = _details
        monkeypatch.setitem(
            sys.modules, "web.backend.services.ai_market_protocol.on_chain", mod
        )
        out = ch._verify_tx_onchain(
            tx_hash="0xabc", amount_usd=5.0, chain="base", token="USDC"
        )
        assert out == {"ok": True, "sender": _EVM_PAYER}
        assert calls and calls[0]["amount_usd"] == 5.0

    def test_verifier_error_fails_closed(self, tmp_db, monkeypatch):
        import sys
        import types

        import aimarket_hub.channels as ch

        mod = types.ModuleType("web.backend.services.ai_market_protocol.on_chain")

        def _boom(**kw):
            raise RuntimeError("rpc down")

        mod.verify_tx_payment_details = _boom
        monkeypatch.setitem(
            sys.modules, "web.backend.services.ai_market_protocol.on_chain", mod
        )
        out = ch._verify_tx_onchain(
            tx_hash="0xabc", amount_usd=5.0, chain="base", token="USDC"
        )
        assert out["ok"] is False and "unavailable" in out["error"]


class TestPayerProofOfControl:
    """SEC (PAYAUTH-003b): matching the on-chain sender is NOT proof of control.

    The payer's address is public — it is printed in the very transaction the claimant
    quotes — so a front-runner names the victim's own address, the sender check passes,
    and open() hands THEM the channel_secret. The invoke path authorizes debits on
    channel id + secret alone (api.py passes no wallet), so that is a full drain of the
    victim's deposit plus a lock-out via the single-use guard.
    """

    def _ledger(self, tmp_db, monkeypatch, **kw):
        import aimarket_hub.channels as ch
        _prod_mode(monkeypatch, ch, **kw)
        return ch.ChannelLedger(db_path=tmp_db)

    def test_front_runner_without_the_payers_key_is_refused(self, tmp_db, monkeypatch):
        # The attacker knows everything public: the tx hash and the payer address.
        # What they cannot produce is a signature by the paying wallet.
        led = self._ledger(tmp_db, monkeypatch)
        try:
            stolen = led.open(5.0, wallet=_EVM_PAYER, tx_hash="0xvictimtx")
            assert "error" in stolen, f"deposit front-running still works: {stolen}"
            assert "payer proof" in stolen["error"]
            # the deposit must NOT be consumed — the victim can still claim it
            assert led.stats()["open_channels"] == 0
            real = led.open(5.0, tx_hash="0xvictimtx", **_PROOF)
            assert "channel" in real, real
            assert real["channel"]["wallet"] == _EVM_PAYER
        finally:
            led.stop_sweep()

    def test_signature_from_a_different_wallet_is_refused(self, tmp_db, monkeypatch):
        # A valid signature that recovers to somebody else proves control of the wrong
        # key — it must not unlock the payer's deposit.
        led = self._ledger(tmp_db, monkeypatch, proof_signer=_EVM_OTHER)
        try:
            r = led.open(5.0, tx_hash="0xwrongsigner", **_PROOF)
            assert "error" in r and "payer proof" in r["error"]
        finally:
            led.stop_sweep()

    def test_unrecoverable_signature_fails_closed(self, tmp_db, monkeypatch):
        led = self._ledger(tmp_db, monkeypatch)
        try:
            r = led.open(5.0, wallet=_EVM_PAYER, tx_hash="0xgarbagesig",
                         payer_signature="0xnot-a-signature")
            assert "error" in r and "payer proof" in r["error"]
        finally:
            led.stop_sweep()

    def test_non_evm_payer_is_refused_not_credited(self, tmp_db, monkeypatch):
        # No proof-of-control scheme is implemented for base58 payers; crediting them
        # unproven would reopen the front-running hole on Solana only.
        led = self._ledger(tmp_db, monkeypatch, sender="5KtPn1SolanaPayer")
        try:
            r = led.open(5.0, chain="solana", tx_hash="5sig", wallet="",
                         payer_signature=_GOOD_SIG)
            assert "error" in r, r
            assert "only implemented for EVM" in r["error"]
            assert led.stats()["open_channels"] == 0
        finally:
            led.stop_sweep()

    def test_recovery_helper_fails_closed_when_primitive_is_missing(self, monkeypatch):
        import sys
        import types

        import aimarket_hub.channels as ch

        # A standalone hub without eth_account / the web package must not treat an
        # un-evaluatable proof as a passing one.
        mod = types.ModuleType("web.backend.services.ai_market_protocol.on_chain")
        monkeypatch.setitem(
            sys.modules, "web.backend.services.ai_market_protocol.on_chain", mod
        )
        assert ch._recover_payer_address(
            payer=_EVM_PAYER, tx_hash="0xabc", chain="base", deposit_usd=5.0,
            signature=_GOOD_SIG,
        ) is None
        # ...and an empty signature never reaches the primitive at all
        assert ch._recover_payer_address(
            payer=_EVM_PAYER, tx_hash="0xabc", chain="base", deposit_usd=5.0,
            signature="  ",
        ) is None

    def test_challenge_degrades_instead_of_raising_importerror(self, monkeypatch):
        """A standalone hub (no `web` package) must not blow up in the helper.

        Every other cross-package import in channels.py degrades to a refusal; this
        one was a bare `from web... import`, so on a standalone deploy it raised
        ImportError straight out of the helper instead of failing closed.
        """
        import builtins
        import sys

        import aimarket_hub.channels as ch

        monkeypatch.delitem(sys.modules, ch._ON_CHAIN_MODULE, raising=False)
        real_import = builtins.__import__

        def _no_web(name, *args, **kwargs):
            if name.startswith(ch._ON_CHAIN_MODULE):
                raise ImportError("no web package in this deployment")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _no_web)
        # A standalone hub now STATES the challenge from its own byte-identical copy
        # instead of degrading to "". Returning "" was safe but useless: it told a paying
        # client nothing to sign, and combined with the missing deposit verifier it meant
        # the deposit door could never open on a hub-only image. Parity with the canonical
        # message is pinned in tests/test_payer_proof.py.
        challenge = ch.payer_proof_challenge(
            payer=_EVM_PAYER, tx_hash="0xabc", chain="base", deposit_usd=1.0
        )
        assert challenge.startswith("AIMarket-Payer-Proof/v1")
        assert "amount_cents:100" in challenge
        # …and a signature over the WRONG message is still unproven, so nothing is credited
        # on a mismatched proof.
        assert ch._recover_payer_address(
            payer=_EVM_PAYER, tx_hash="0xabc", chain="base", deposit_usd=1.0,
            signature=_GOOD_SIG,
        ) is None

    def test_escape_hatch_is_off_by_default_and_loud_when_on(self, tmp_db, monkeypatch):
        led = self._ledger(tmp_db, monkeypatch)
        try:
            assert "error" in led.open(5.0, wallet=_EVM_PAYER, tx_hash="0xhatch")
            monkeypatch.setenv("AIMARKET_CHANNEL_ALLOW_UNPROVEN_PAYER", "1")
            r = led.open(5.0, wallet=_EVM_PAYER, tx_hash="0xhatch")
            assert "channel" in r, r
            # anything other than an explicit "1" keeps the gate closed
            for value in ("", "0", "true", "yes"):
                monkeypatch.setenv("AIMARKET_CHANNEL_ALLOW_UNPROVEN_PAYER", value)
                assert "error" in led.open(5.0, wallet=_EVM_PAYER, tx_hash=f"0xh_{value}")
        finally:
            led.stop_sweep()

    def test_stub_and_demo_paths_are_unaffected(self, ledger):
        # Dev/demo channels carry no real deposit to front-run; requiring a signature
        # there would break every local run.
        assert "channel" in ledger.open(1.0, wallet=_EVM_PAYER)


# ── Payout obligations (ACCT-001) ────────────────────────────────

class TestPayoutObligations:
    """ACCT-001: nothing here transfers funds, so an unreturned remainder must be
    recorded as an explicit debt instead of logged as a "refund"."""

    def test_close_records_obligation_and_reports_owed(self, ledger):
        opened = ledger.open(5.0, wallet="0xAlice")["channel"]
        cid = opened["channel_id"]
        ledger.debit(cid, 2.0, receipt_id="obl_1", secret=opened["channel_secret"])
        s = ledger.close(cid, wallet="0xAlice", secret=opened["channel_secret"])["settlement"]

        assert s["refund_usd"] == 3.0            # back-compat key = remainder
        assert s["refund_executed_usd"] == 0.0   # the hub never moved money
        assert s["refund_owed_usd"] == 3.0
        assert s["refund_status"] == "owed"
        assert s["obligation"]["amount_usd"] == 3.0
        assert s["obligation"]["status"] == "owed"
        assert s["obligation"]["wallet"] == "0xAlice"

        owed = ledger.obligations()
        assert [o["channel_id"] for o in owed] == [cid]
        assert ledger.obligations_total()["total_usd"] == 3.0
        assert ledger.stats()["outstanding_obligations_usd"] == 3.0

    def test_fully_spent_channel_owes_nothing(self, ledger):
        opened = ledger.open(1.0, wallet="0xAlice")["channel"]
        cid = opened["channel_id"]
        ledger.debit(cid, 1.0, receipt_id="obl_spent", secret=opened["channel_secret"])
        s = ledger.close(cid, wallet="0xAlice", secret=opened["channel_secret"])["settlement"]
        assert s["refund_status"] == "none"
        assert s["obligation"] is None
        assert ledger.obligations() == []

    def test_obligation_is_idempotent(self, ledger):
        opened = ledger.open(4.0, wallet="0xAlice")["channel"]
        cid = opened["channel_id"]
        ledger.close(cid, wallet="0xAlice", secret=opened["channel_secret"])
        # A crash-and-retry (or a second sweep pass) must not double-book the debt.
        with ledger._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM channels WHERE channel_id = ?", (cid,)
            ).fetchone()
            again = ledger._record_payout_obligation(
                conn, row, kind="close_remainder", now="2026-01-01T00:00:00Z",
            )
            conn.commit()
        assert again["amount_usd"] == 4.0
        assert len(ledger.obligations()) == 1
        assert ledger.obligations_total()["count"] == 1

    def test_expiry_sweep_owes_only_the_unspent_part(self, ledger):
        opened = ledger.open(10.0, wallet="0xAlice")["channel"]
        cid = opened["channel_id"]
        ledger.debit(cid, 4.0, receipt_id="obl_exp", secret=opened["channel_secret"])
        with ledger._get_conn() as conn:
            conn.execute(
                "UPDATE channels SET expires_at = '2000-01-01T00:00:00Z' "
                "WHERE channel_id = ?", (cid,),
            )
            conn.commit()

        assert ledger._sweep_expired() == 1
        assert ledger.get(cid)["status"] == "expired"
        owed = ledger.obligations()
        assert len(owed) == 1
        # 6.00 unspent — NOT 10.00 (the old log printed balance + used)
        assert owed[0]["amount_usd"] == 6.0
        assert owed[0]["kind"] == "expiry_remainder"

    def test_expired_volume_is_counted(self, ledger):
        opened = ledger.open(10.0, wallet="0xAlice")["channel"]
        cid = opened["channel_id"]
        ledger.debit(cid, 4.0, receipt_id="obl_vol", secret=opened["channel_secret"])
        with ledger._get_conn() as conn:
            conn.execute(
                "UPDATE channels SET expires_at = '2000-01-01T00:00:00Z' "
                "WHERE channel_id = ?", (cid,),
            )
            conn.commit()
        ledger._sweep_expired()
        s = ledger.stats()
        assert s["expired_channels"] == 1
        assert s["expired_volume_usd"] == 4.0
        assert s["closed_volume_usd"] == 4.0   # settled + expired, nothing dropped

    def test_mark_paid_requires_tx_hash_and_is_single_shot(self, ledger):
        opened = ledger.open(2.0, wallet="0xAlice")["channel"]
        cid = opened["channel_id"]
        ledger.close(cid, wallet="0xAlice", secret=opened["channel_secret"])

        payout = "0x" + "11" * 32
        assert "error" in ledger.mark_obligation_paid(cid, "")
        assert ledger.mark_obligation_paid(cid, payout).get("ok")
        assert ledger.obligations("owed") == []
        paid = ledger.obligations("paid")
        assert paid[0]["payout_tx_hash"] == payout
        # already settled → no outstanding obligation to mark
        assert "error" in ledger.mark_obligation_paid(cid, "0x" + "22" * 32)
        assert "error" in ledger.mark_obligation_paid("ch_nope", payout)

    def test_module_level_obligation_readers(self, monkeypatch):
        import uuid
        monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", _OPERATOR_TOKEN)
        wallet = f"0xOblMod_{uuid.uuid4().hex[:6]}"
        opened = open_channel(1.0, wallet=wallet)["channel"]
        cid = opened["channel_id"]
        close_channel(cid, wallet=wallet, secret=opened["channel_secret"])
        listed = [
            o for o in channel_obligations(limit=5_000, operator_token=_OPERATOR_TOKEN)
            if o["channel_id"] == cid
        ]
        assert listed and listed[0]["amount_usd"] == 1.0
        assert channel_obligations_total(operator_token=_OPERATOR_TOKEN)["total_usd"] >= 1.0


_OPERATOR_TOKEN = "operator-token-not-for-production"


class TestObligationExportsAreOperatorGated:
    """The liability ledger names depositors and writes off their claims.

    The HTTP routes gate it, but the module-level exports are importable by any
    in-process plugin — so gating only the routes would leave the export as the weak
    spot. mark_obligation_paid in particular used to flip a real debt to 'paid' with
    no authorization at all, on any non-empty string.
    """

    @pytest.fixture
    def owed(self, ledger, monkeypatch, tmp_db):
        import aimarket_hub.channels as ch
        monkeypatch.setattr(ch, "_ledger", ledger)
        monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", _OPERATOR_TOKEN)
        opened = ledger.open(2.0, wallet="0xAlice", chain="base")["channel"]
        cid = opened["channel_id"]
        ledger.close(cid, wallet="0xAlice", secret=opened["channel_secret"])
        return cid

    def test_readers_refuse_without_the_operator_token(self, owed):
        import aimarket_hub.channels as ch
        with pytest.raises(PermissionError):
            ch.channel_obligations()
        with pytest.raises(PermissionError):
            ch.channel_obligations(operator_token="guessed")
        with pytest.raises(PermissionError):
            ch.channel_obligations_total()
        assert ch.channel_obligations(operator_token=_OPERATOR_TOKEN)[0]["channel_id"] == owed

    def test_writer_refuses_without_the_operator_token(self, owed, ledger):
        import aimarket_hub.channels as ch
        with pytest.raises(PermissionError):
            ch.mark_obligation_paid(owed, "0x" + "ab" * 32)
        with pytest.raises(PermissionError):
            ch.mark_obligation_paid(owed, "0x" + "ab" * 32, operator_token="guessed")
        # the debt is untouched
        assert ledger.obligations()[0]["status"] == "owed"

    def test_unconfigured_admin_token_authorizes_nobody(self, owed, monkeypatch):
        import aimarket_hub.channels as ch
        monkeypatch.delenv("AIMARKET_ADMIN_TOKEN", raising=False)
        # Fail closed: with nothing to authenticate against, an empty token must not
        # match the empty expectation.
        with pytest.raises(PermissionError):
            ch.channel_obligations(operator_token="")
        with pytest.raises(PermissionError):
            ch.mark_obligation_paid(owed, "0x" + "ab" * 32, operator_token="")

    def test_writer_is_crypto_gated(self, owed, monkeypatch, ledger):
        import aimarket_hub.channels as ch
        monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "0")
        out = ch.mark_obligation_paid(
            owed, "0x" + "ab" * 32, operator_token=_OPERATOR_TOKEN
        )
        assert "error" in out and "disabled" in out["error"]
        assert ledger.obligations()[0]["status"] == "owed"

    def test_payout_hash_must_be_shaped_like_a_transaction(self, owed, ledger):
        import aimarket_hub.channels as ch
        for junk in ("paid", "done", "0xshort", "0x" + "zz" * 32, "0x" + "ab" * 31):
            out = ch.mark_obligation_paid(owed, junk, operator_token=_OPERATOR_TOKEN)
            assert "error" in out, junk
            assert ledger.obligations()[0]["status"] == "owed", junk
        good = ch.mark_obligation_paid(
            owed, "0x" + "Ab" * 32, operator_token=_OPERATOR_TOKEN
        )
        assert good.get("ok"), good
        assert ledger.obligations("paid")[0]["payout_tx_hash"] == "0x" + "Ab" * 32

    def test_non_evm_payout_hash_accepts_a_base58_signature(self, ledger, monkeypatch):
        import aimarket_hub.channels as ch
        monkeypatch.setattr(ch, "_ledger", ledger)
        monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", _OPERATOR_TOKEN)
        opened = ledger.open(1.0, wallet="5KtPn1SolanaPayer", chain="solana")["channel"]
        cid = opened["channel_id"]
        ledger.close(cid, wallet="5KtPn1SolanaPayer", secret=opened["channel_secret"])
        assert "error" in ch.mark_obligation_paid(cid, "sent", operator_token=_OPERATOR_TOKEN)
        sig = "5" + "j" * 86
        assert ch.mark_obligation_paid(cid, sig, operator_token=_OPERATOR_TOKEN).get("ok")


# ── Orphaned-hold reaper ─────────────────────────────────────────

def _make_settlements_db(path, rows=()):
    """A minimal hub-index DB carrying the verified_settlements table the reaper reads."""
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE verified_settlements ("
        " nonce TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'pending')"
    )
    for nonce, status in rows:
        conn.execute(
            "INSERT INTO verified_settlements (nonce, status) VALUES (?, ?)",
            (nonce, status),
        )
    conn.commit()
    conn.close()


def _age_hold(ledger, receipt_id, iso="2000-01-01T00:00:00Z"):
    with ledger._get_conn() as conn:
        conn.execute(
            "UPDATE channel_holds SET created_at = ? WHERE receipt_id = ?",
            (iso, receipt_id),
        )
        conn.commit()


class TestOrphanedHoldReaper:
    """A hold committed to the ledger DB with no verified_settlements row in the hub DB
    (hard kill between the two commits) used to freeze the buyer's balance forever:
    reconcile() only re-queues rows that exist, close() refuses while a hold is 'held',
    and the expiry sweep skips such channels."""

    @pytest.fixture
    def env(self, ledger, tmp_path, monkeypatch):
        settle_db = tmp_path / "hub.db"
        monkeypatch.setenv("AIMARKET_VERIFY_SETTLEMENTS_DB_PATH", str(settle_db))
        return {"ledger": ledger, "settle_db": settle_db}

    def test_orphaned_hold_is_released_and_reap_is_idempotent(self, env):
        led, settle_db = env["ledger"], env["settle_db"]
        _make_settlements_db(str(settle_db))          # no row for our receipt = orphan
        opened = led.open(5.0, wallet="0xAlice")["channel"]
        cid = opened["channel_id"]
        assert led.hold(cid, 2.0, receipt_id="orphan_1", secret=opened["channel_secret"])["ok"]
        assert led.get(cid)["balance_usd"] == 3.0
        # close is blocked while the hold hangs — the frozen-balance symptom
        assert "pending verified settlement" in led.close(cid, wallet="0xAlice", secret=opened["channel_secret"])["error"]

        _age_hold(led, "orphan_1")
        out = led.reap_stale_holds()
        assert out["reaped"] == 1
        assert out["released_usd"] == 2.0
        assert led.get(cid)["balance_usd"] == 5.0

        with led._get_conn() as conn:
            row = conn.execute(
                "SELECT status, resolution_note FROM channel_holds WHERE receipt_id = ?",
                ("orphan_1",),
            ).fetchone()
        assert row["status"] == "reaped"
        assert "no live verification" in row["resolution_note"]

        # second pass must not credit the balance again
        assert led.reap_stale_holds()["reaped"] == 0
        assert led.get(cid)["balance_usd"] == 5.0
        # ...and the channel can finally be closed
        assert "settlement" in led.close(cid, wallet="0xAlice", secret=opened["channel_secret"])

    @pytest.mark.parametrize("status", ["pending", "verifying"])
    def test_live_verification_hold_is_never_released(self, env, status):
        led, settle_db = env["ledger"], env["settle_db"]
        opened = led.open(5.0, wallet="0xAlice")["channel"]
        cid = opened["channel_id"]
        led.hold(cid, 2.0, receipt_id="live_1", secret=opened["channel_secret"])
        _make_settlements_db(str(settle_db), rows=[("live_1", status)])
        _age_hold(led, "live_1")

        out = led.reap_stale_holds()
        assert out["reaped"] == 0
        assert out["skipped"] == 1
        assert led.get(cid)["balance_usd"] == 3.0

    def test_resolved_settlement_row_does_not_protect_a_stuck_hold(self, env):
        # The verification finished but the hold never resolved → nothing owns it.
        led, settle_db = env["ledger"], env["settle_db"]
        opened = led.open(5.0, wallet="0xAlice")["channel"]
        cid = opened["channel_id"]
        led.hold(cid, 2.0, receipt_id="done_1", secret=opened["channel_secret"])
        _make_settlements_db(str(settle_db), rows=[("done_1", "refunded")])
        _age_hold(led, "done_1")
        assert led.reap_stale_holds()["reaped"] == 1
        assert led.get(cid)["balance_usd"] == 5.0

    def test_fresh_hold_is_not_reaped(self, env):
        led, settle_db = env["ledger"], env["settle_db"]
        _make_settlements_db(str(settle_db))
        opened = led.open(5.0, wallet="0xAlice")["channel"]
        cid = opened["channel_id"]
        led.hold(cid, 2.0, receipt_id="fresh_1", secret=opened["channel_secret"])
        assert led.reap_stale_holds()["reaped"] == 0
        assert led.get(cid)["balance_usd"] == 3.0

    def test_unreadable_settlements_db_reaps_nothing(self, env):
        # Cannot evaluate ownership → refuse (releasing a hold a live verification later
        # captures would let the same cents be spent twice).
        led = env["ledger"]  # settle_db deliberately never created
        opened = led.open(5.0, wallet="0xAlice")["channel"]
        cid = opened["channel_id"]
        led.hold(cid, 2.0, receipt_id="blind_1", secret=opened["channel_secret"])
        _age_hold(led, "blind_1")
        out = led.reap_stale_holds()
        assert out["reaped"] == 0
        assert "error" in out
        assert led.get(cid)["balance_usd"] == 3.0

    def test_missing_settlements_table_reaps_nothing(self, env, tmp_path):
        led, settle_db = env["ledger"], env["settle_db"]
        sqlite3.connect(str(settle_db)).close()   # exists, but no verified_settlements
        opened = led.open(5.0, wallet="0xAlice")["channel"]
        cid = opened["channel_id"]
        led.hold(cid, 2.0, receipt_id="notable_1", secret=opened["channel_secret"])
        _age_hold(led, "notable_1")
        assert led.reap_stale_holds()["reaped"] == 0
        assert led.get(cid)["balance_usd"] == 3.0

    def test_partially_captured_hold_is_refused(self, env):
        led, settle_db = env["ledger"], env["settle_db"]
        _make_settlements_db(str(settle_db))
        opened = led.open(5.0, wallet="0xAlice")["channel"]
        cid = opened["channel_id"]
        led.hold(cid, 2.0, receipt_id="halfcap_1", secret=opened["channel_secret"])
        # Simulate a crash mid-capture: debit receipt written, hold still 'held'.
        with led._get_conn() as conn:
            conn.execute(
                "INSERT INTO debited_receipts (receipt_id, channel_id, amount_cents, "
                "timestamp) VALUES (?, ?, ?, ?)",
                ("halfcap_1", cid, 200, "2000-01-01T00:00:00Z"),
            )
            conn.commit()
        _age_hold(led, "halfcap_1")

        out = led.reap_stale_holds()
        assert out["reaped"] == 0
        assert out.get("inconsistent") == 1
        assert led.get(cid)["balance_usd"] == 3.0

    def test_capture_after_scan_wins_over_reaper(self, env):
        led, settle_db = env["ledger"], env["settle_db"]
        _make_settlements_db(str(settle_db))
        opened = led.open(5.0, wallet="0xAlice")["channel"]
        cid = opened["channel_id"]
        led.hold(cid, 2.0, receipt_id="race_1", secret=opened["channel_secret"])
        _age_hold(led, "race_1")
        assert led.capture_hold("race_1")["ok"]
        # the hold is no longer 'held', so the reaper must not resurrect the cents
        assert led.reap_stale_holds()["reaped"] == 0
        assert led.get(cid)["balance_usd"] == 3.0
        assert led.get(cid)["used_usd"] == 2.0

    def test_reaper_can_be_disabled(self, env, monkeypatch):
        led, settle_db = env["ledger"], env["settle_db"]
        _make_settlements_db(str(settle_db))
        opened = led.open(5.0, wallet="0xAlice")["channel"]
        cid = opened["channel_id"]
        led.hold(cid, 2.0, receipt_id="off_1", secret=opened["channel_secret"])
        _age_hold(led, "off_1")
        monkeypatch.setenv("AIMARKET_CHANNEL_HOLD_REAP_AFTER_SECS", "0")
        out = led.reap_stale_holds()
        assert out["disabled"] is True and out["reaped"] == 0
        assert led.get(cid)["balance_usd"] == 3.0

    def test_age_knob_is_honoured(self, env, monkeypatch):
        led, settle_db = env["ledger"], env["settle_db"]
        _make_settlements_db(str(settle_db))
        opened = led.open(5.0, wallet="0xAlice")["channel"]
        cid = opened["channel_id"]
        led.hold(cid, 2.0, receipt_id="knob_1", secret=opened["channel_secret"])
        # created_at is "now" → a 1-hour threshold keeps it, a 0-second-age explicit
        # call would reap it, and the env knob drives the default.
        monkeypatch.setenv("AIMARKET_CHANNEL_HOLD_REAP_AFTER_SECS", "3600")
        assert led.reap_stale_holds()["reaped"] == 0
        _age_hold(led, "knob_1", iso=time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 7200)))
        assert led.reap_stale_holds()["reaped"] == 1

    def test_sqlite_default_timestamp_format_is_aged_correctly(self, env):
        # A row written by the column DEFAULT uses "YYYY-MM-DD HH:MM:SS"; comparing that
        # to an ISO-T cutoff as TEXT would age a brand-new hold out immediately.
        led, settle_db = env["ledger"], env["settle_db"]
        _make_settlements_db(str(settle_db))
        opened = led.open(5.0, wallet="0xAlice")["channel"]
        cid = opened["channel_id"]
        led.hold(cid, 2.0, receipt_id="fmt_1", secret=opened["channel_secret"])
        _age_hold(led, "fmt_1", iso=time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()))
        assert led.reap_stale_holds()["reaped"] == 0
        _age_hold(led, "fmt_1", iso="2000-01-01 00:00:00")
        assert led.reap_stale_holds()["reaped"] == 1


# ── Hardening of the remaining sharp edges ───────────────────────

class TestOpenValidation:
    def test_non_finite_deposit_is_rejected_not_raised(self, ledger):
        for bad in (float("nan"), float("inf"), float("-inf")):
            r = ledger.open(bad, wallet="0xAlice")
            assert "error" in r, bad
            assert "finite" in r["error"], r
        assert ledger.stats()["open_channels"] == 0

    def test_non_numeric_deposit_is_rejected(self, ledger):
        assert "error" in ledger.open("five")  # type: ignore[arg-type]


class TestRateLimitBounds:
    """The limiter used to exempt wallet-less callers entirely — a public hub was
    effectively unlimited to anyone who simply omitted the wallet field."""

    def test_anonymous_opens_share_a_bounded_bucket(self, ledger, monkeypatch):
        monkeypatch.setenv("AIMARKET_CHANNEL_ANON_OPENS_PER_HOUR", "3")
        for i in range(3):
            assert "channel" in ledger.open(0.10), i
        r = ledger.open(0.10)
        assert "error" in r and "rate limit" in r["error"]
        # a named wallet has its own bucket and is unaffected
        assert "channel" in ledger.open(0.10, wallet="0xAlice")

    def test_anonymous_closes_are_bounded(self, ledger, monkeypatch):
        opened = [ledger.open(0.10)["channel"] for _ in range(3)]
        cids = [ch["channel_id"] for ch in opened]
        monkeypatch.setenv("AIMARKET_CHANNEL_ANON_CLOSES_PER_HOUR", "2")
        ledger._close_rate.clear()
        assert "settlement" in ledger.close(cids[0], secret=opened[0]["channel_secret"])
        assert "settlement" in ledger.close(cids[1], secret=opened[1]["channel_secret"])
        assert "error" in ledger.close(cids[2], secret=opened[2]["channel_secret"])

    def test_zero_cap_fails_closed(self, ledger, monkeypatch):
        monkeypatch.setenv("AIMARKET_CHANNEL_ANON_OPENS_PER_HOUR", "0")
        # 0 = no allowance; refuse rather than fall back to "unlimited"
        assert "rate limit" in ledger.open(0.10)["error"]

    def test_full_tracking_table_evicts_instead_of_refusing(self, ledger, monkeypatch):
        """A full bucket table must never lock real depositors out.

        The bucket key is caller-supplied and is charged BEFORE any verification, so
        refusing when the table filled up turned ~50k junk wallet strings into a total
        availability outage: every genuine wallet was refused open AND close for an
        hour. Evicting the least-recently-active bucket keeps the door open.
        """
        import aimarket_hub.channels as ch
        monkeypatch.setattr(ch, "_MAX_RATE_TRACKED_KEYS", 2)
        assert "channel" in ledger.open(0.10, wallet="0xFlood1")
        assert "channel" in ledger.open(0.10, wallet="0xFlood2")
        # table full of live buckets → the NEW wallet is served, an old one is evicted
        r = ledger.open(0.10, wallet="0xRealDepositor")
        assert "channel" in r, r
        assert "0xRealDepositor" in ledger._rate_state
        assert len(ledger._rate_state) <= 2
        # ...and the per-wallet limit itself still bites for the surviving key
        for _ in range(19):
            ledger.open(0.10, wallet="0xRealDepositor")
        assert "rate limit" in ledger.open(0.10, wallet="0xRealDepositor")["error"]

    def test_eviction_never_drops_the_caller_being_charged(self, ledger, monkeypatch):
        """Evicting the bucket we just charged would hand that caller a fresh window."""
        import aimarket_hub.channels as ch
        monkeypatch.setattr(ch, "_MAX_RATE_TRACKED_KEYS", 1)
        for i in range(5):
            assert "channel" in ledger.open(0.10, wallet="0xSame")
        assert "0xSame" in ledger._rate_state
        assert len(ledger._rate_state["0xSame"]) == 5

    def test_close_is_not_locked_out_by_a_full_table(self, ledger, monkeypatch):
        """The outage hit close() too — a depositor could not even settle out."""
        import aimarket_hub.channels as ch
        opened = ledger.open(1.0, wallet="0xSettler")["channel"]
        cid = opened["channel_id"]
        monkeypatch.setattr(ch, "_MAX_RATE_TRACKED_KEYS", 1)
        ledger._close_rate.clear()
        ledger._close_rate["0xJunk1"] = [time.time()]
        assert "settlement" in ledger.close(cid, wallet="0xSettler", secret=opened["channel_secret"])

    def test_stale_buckets_are_pruned(self, ledger):
        ledger._rate_state["0xOld"] = [time.time() - 7200]
        ledger._prune_rate_store(ledger._rate_state, time.time() - 3600)
        assert "0xOld" not in ledger._rate_state

    def test_shared_anonymous_bucket_is_never_evicted(self, ledger, monkeypatch):
        """Evicting the shared bucket would reset the anonymous cap on demand."""
        import aimarket_hub.channels as ch
        monkeypatch.setenv("AIMARKET_CHANNEL_ANON_OPENS_PER_HOUR", "2")
        monkeypatch.setattr(ch, "_MAX_RATE_TRACKED_KEYS", 1)
        assert "channel" in ledger.open(0.10)
        assert "channel" in ledger.open(0.10)
        # named wallets churn through the table but must not flush the anon bucket
        for i in range(5):
            ledger.open(0.10, wallet=f"0xChurn{i}")
        assert "rate limit" in ledger.open(0.10)["error"]


class TestRefundHardening:
    def test_refund_requires_channel_secret_when_one_exists(self, ledger):
        r = ledger.open(5.0, wallet="0xAlice", with_secret=True)["channel"]
        cid, sec = r["channel_id"], r["channel_secret"]
        ledger.debit(cid, 2.0, secret=sec, receipt_id="rf_1")
        assert "error" in ledger.refund(cid, 1.0)
        assert "error" in ledger.refund(cid, 1.0, secret="wrong")
        assert ledger.refund(cid, 1.0, secret=sec).get("ok")

    def test_refund_rejects_wrong_requester_wallet(self, ledger):
        opened = ledger.open(5.0, wallet="0xAlice")["channel"]
        cid = opened["channel_id"]
        ledger.debit(cid, 2.0, receipt_id="rf_2", secret=opened["channel_secret"])
        assert "error" in ledger.refund(cid, 1.0, requester_wallet="0xMallory", secret=opened["channel_secret"])
        assert ledger.refund(cid, 1.0, requester_wallet="0xAlice", secret=opened["channel_secret"]).get("ok")

    def test_refund_cannot_return_held_cents(self, ledger):
        """The old cap (original - balance) counted cents reserved by a hold, so
        refunding them put them back in the spendable balance while the hold could
        still be captured — value the deposit never covered."""
        opened = ledger.open(5.0, wallet="0xAlice")["channel"]
        cid = opened["channel_id"]
        assert ledger.hold(cid, 5.0, receipt_id="hold_rf", secret=opened["channel_secret"])["ok"]
        assert ledger.get(cid)["balance_usd"] == 0.0
        assert "error" in ledger.refund(cid, 5.0, secret=opened["channel_secret"])     # nothing spent yet → nothing to reverse
        assert ledger.get(cid)["balance_usd"] == 0.0

    def test_module_refund_is_crypto_gated(self, monkeypatch):
        import uuid
        wallet = f"0xRfGate_{uuid.uuid4().hex[:6]}"
        r = open_channel(2.0, wallet=wallet)["channel"]
        monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "0")
        out = refund_channel(r["channel_id"], 1.0, secret=r["channel_secret"])
        assert "error" in out and "disabled" in out["error"]


class TestChannelMigrationPin:
    """The ledger owns a separate DB file, so it applies a SUBSET of the registry. That
    subset must be derived from the DDL — a hand-written target_version silently skips
    the next channels migration."""

    def test_derived_set_covers_every_channel_table(self):
        from aimarket_hub import migrations as mig
        versions = mig.channel_ledger_versions()
        for expected in (4, 7, 12, 14, 17):
            assert expected in versions, versions

    def test_a_new_channels_migration_is_picked_up_automatically(self, monkeypatch):
        from aimarket_hub import migrations as mig
        fake = (999, "999_future_channels", "ALTER TABLE channels ADD COLUMN zz TEXT;", "")
        other = (998, "998_unrelated", "ALTER TABLE peers ADD COLUMN zz TEXT;", "")
        monkeypatch.setattr(mig, "MIGRATIONS", list(mig.MIGRATIONS) + [fake, other])
        versions = mig.channel_ledger_versions()
        assert 999 in versions       # would be skipped by a stale target_version pin
        assert 998 not in versions   # unrelated tables stay out of the ledger DB

    def test_column_named_channel_id_does_not_count_as_the_channels_table(self):
        from aimarket_hub import migrations as mig
        assert mig._touches_table("CREATE TABLE x (channel_id TEXT);", "channels") is False
        assert mig._touches_table("CREATE INDEX idx_channels_status ON x(y);", "channels") is False
        assert mig._touches_table("ALTER TABLE channels ADD COLUMN z TEXT;", "channels") is True

    def test_ledger_db_has_exactly_the_channel_migrations(self, tmp_db):
        from aimarket_hub import migrations as mig
        led = ChannelLedger(db_path=tmp_db)
        try:
            with led._get_conn() as conn:
                applied = {r[0] for r in conn.execute("SELECT version FROM _migrations")}
                tables = {
                    r[0] for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            assert applied == set(mig.channel_ledger_versions())
            for table in mig.CHANNEL_LEDGER_TABLES:
                assert table in tables, table
        finally:
            led.stop_sweep()


class TestFactoryWalletSettlementAccounting:
    """ACCT-001 consumer side: `close` moves NO funds, so the remainder is a
    RECEIVABLE, not a balance.

    settle_channel read `refund_usd` (the remainder) straight into balance_usd and
    logged "Refund: $X" — booking money it does not have and reporting a transfer
    nobody made. Only `refund_executed_usd` can be a balance.
    """

    def _wallet(self, tmp_path, settlement, monkeypatch):
        import httpx

        from aimarket_hub.factory_wallet import FactoryWallet

        monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")
        monkeypatch.setenv("AIMARKET_PAYMENT_RECIPIENT", "0x" + "ab" * 20)

        class _Resp:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"settlement": settlement}

        monkeypatch.setattr(httpx, "post", lambda *a, **kw: _Resp())
        wallet = FactoryWallet(tmp_path / "wallet.json")
        wallet._balance.channel_id = "ch_settle_test"
        wallet._balance.balance_usd = _to_decimal_for_test(9.0)
        return wallet

    def test_unpaid_remainder_is_a_receivable_not_a_balance(self, tmp_path, monkeypatch):
        wallet = self._wallet(tmp_path, {
            "channel_id": "ch_settle_test", "used_usd": 1.0,
            "refund_usd": 9.0, "refund_executed_usd": 0.0, "refund_owed_usd": 9.0,
            "refund_status": "owed",
        }, monkeypatch)
        out = wallet.settle_channel()
        assert out["success"] is True
        assert out["refund_executed_usd"] == 0.0
        assert out["refund_owed_usd"] == 9.0
        # the whole point: the factory does NOT have $9 back
        assert float(wallet.get_balance().balance_usd) == 0.0
        assert float(wallet.get_balance().refund_owed_usd) == 9.0
        assert wallet.report()["refund_owed_usd"] == 9.0
        # ...and the ledger line says "owed", not "Refund: $9.00"
        note = wallet.report()["recent_transactions"][-1]["description"]
        assert "owed $9.00" in note and "no funds moved" in note

    def test_an_executed_refund_does_credit_the_balance(self, tmp_path, monkeypatch):
        """If a hub ever does execute the payout, honest accounting must record it."""
        wallet = self._wallet(tmp_path, {
            "refund_usd": 9.0, "refund_executed_usd": 9.0, "refund_owed_usd": 0.0,
            "refund_status": "paid",
        }, monkeypatch)
        wallet.settle_channel()
        assert float(wallet.get_balance().balance_usd) == 9.0
        assert float(wallet.get_balance().refund_owed_usd) == 0.0

    def test_sale_earnings_are_not_wiped_by_a_settlement(self, tmp_path, monkeypatch):
        """balance_usd is a running pool, not a mirror of the channel.

        record_sale credits earnings into the SAME field the settlement writes, so
        assigning the settlement figure into it destroyed every sale booked while the
        channel was open. Only the channel's own remainder may leave the pool.
        """
        wallet = self._wallet(tmp_path, {
            "refund_usd": 9.0, "refund_executed_usd": 0.0, "refund_owed_usd": 9.0,
        }, monkeypatch)
        wallet.record_sale("cap-a", 100.0)
        assert float(wallet.get_balance().balance_usd) == 109.0
        wallet.settle_channel()
        # the $9 channel remainder is gone (owed, not returned); the $100 earned is not
        assert float(wallet.get_balance().balance_usd) == 100.0
        assert float(wallet.get_balance().refund_owed_usd) == 9.0

    def test_legacy_settlement_without_the_new_keys_is_treated_as_owed(self, tmp_path, monkeypatch):
        """An older hub reports only `refund_usd`; it still moved no funds.

        The pool held $9 while the hub says only $4 was still in the channel, so $5 of
        it was never channel money and must survive the close.
        """
        wallet = self._wallet(tmp_path, {"refund_usd": 4.0}, monkeypatch)
        wallet.settle_channel()
        assert float(wallet.get_balance().balance_usd) == 5.0
        assert float(wallet.get_balance().refund_owed_usd) == 4.0

    def test_a_stale_local_balance_cannot_go_negative(self, tmp_path, monkeypatch):
        """The hub is authoritative about the remainder; a lagging mirror clamps at 0."""
        wallet = self._wallet(tmp_path, {
            "refund_usd": 40.0, "refund_executed_usd": 0.0, "refund_owed_usd": 40.0,
        }, monkeypatch)
        wallet.settle_channel()
        assert float(wallet.get_balance().balance_usd) == 0.0
        assert float(wallet.get_balance().refund_owed_usd) == 40.0

    def test_receivable_survives_a_restart(self, tmp_path, monkeypatch):
        from aimarket_hub.factory_wallet import FactoryWallet

        wallet = self._wallet(tmp_path, {
            "refund_usd": 3.0, "refund_executed_usd": 0.0, "refund_owed_usd": 3.0,
        }, monkeypatch)
        wallet.settle_channel()
        reloaded = FactoryWallet(tmp_path / "wallet.json")
        assert float(reloaded.get_balance().refund_owed_usd) == 3.0
        # the settled channel id is cleared, so a later purchase cannot try to spend it
        assert reloaded.get_balance().channel_id == ""


def _to_decimal_for_test(value):
    from aimarket_hub.factory_wallet import _to_decimal

    return _to_decimal(value)


class TestRecordedSpendLookup:
    """Deposit binding stores the VERIFIER's rendering of the payer (EIP-55
    checksummed). An exact-match spend lookup therefore found nothing for a self-bond
    registered in lower case, and the slash route refused every production channel with
    "no hub-recorded settlement" — a real gate turned into a permanent 422."""

    def test_evm_spend_is_found_regardless_of_address_case(self, ledger):
        opened = ledger.open(5.0, wallet=_EVM_PAYER)["channel"]
        cid = opened["channel_id"]
        ledger.debit(cid, 2.0, receipt_id="spend_case_1", secret=opened["channel_secret"])
        for form in (_EVM_PAYER, _EVM_PAYER_LOWER, _EVM_PAYER.upper()):
            assert ledger.recorded_spend_usd(form) == 2.0, form

    def test_unknown_wallet_still_returns_none(self, ledger):
        # Fail closed: "no record" must not become "matches everything".
        assert ledger.recorded_spend_usd(_EVM_OTHER) is None
        assert ledger.recorded_spend_usd("") is None

    def test_base58_wallet_stays_case_sensitive(self, ledger):
        opened = ledger.open(1.0, wallet="5KtPn1SolanaPayer")["channel"]
        cid = opened["channel_id"]
        ledger.debit(cid, 1.0, receipt_id="spend_case_2", secret=opened["channel_secret"])
        assert ledger.recorded_spend_usd("5KtPn1SolanaPayer") == 1.0
        assert ledger.recorded_spend_usd("5ktpn1solanapayer") is None


def test_a_debit_that_moves_money_must_name_its_receipt(ledger):
    opened = ledger.open(10.0, wallet="0xAlice")["channel"]
    cid, sec = opened["channel_id"], opened["channel_secret"]
    assert ledger.debit(cid, 1.0, secret=sec)["error"] == "receipt_id is required for a debit"
    assert ledger.debit(cid, 1.0, secret=sec, receipt_id="r-1").get("ok")
    assert "replay" in ledger.debit(cid, 1.0, secret=sec, receipt_id="r-1")["error"]
    # A zero-amount debit only authenticates the secret; it moves nothing and needs no receipt.
    assert ledger.debit(cid, 0.0, secret=sec).get("ok")
