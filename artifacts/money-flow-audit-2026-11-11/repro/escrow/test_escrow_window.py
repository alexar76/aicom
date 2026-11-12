"""Scratch reproductions for the escrow-bridge audit (read-only on the repo).

Run from the scratch dir with AIMARKET_CHANNELS_DB_PATH pointing into it, so importing
aimarket_hub.channels (which builds a global ledger) never writes under the repo.
"""
from __future__ import annotations

import os
import sqlite3

import pytest

from aimarket_hub.escrow_bridge import authorization, chain, mirror, signer as signer_mod, store
from aimarket_hub.escrow_bridge.eip712 import DebitAuthorization
from aimarket_hub.escrow_bridge.errors import AuthorizationRejected

_ESCROW = "0xe7f1725e7734ce288f8367e1bb143e90bb3f0512"
_HUB = "0x70997970c51812dc3a010c7d01b50e0d17dc79c8"
_TOKEN = "0x5fbdb2315678afecb367f032d93f642f64180aa3"
_ESCROW_CHANNEL = "0x" + "11" * 32
_CHAIN_ID = 8453
_ZERO = "0x" + "00" * 20
_DEPOSITOR_KEY = "0x" + "42" * 32
_NOW = 1_000_000
_DEADLINE = _NOW + 3600
_P = 1_000_000  # $1.00 in USDC base units


def _account():
    from eth_account import Account
    return Account.from_key(_DEPOSITOR_KEY)


@pytest.fixture
def st(tmp_path):
    s = store.AuthorizationStore(str(tmp_path / "bridge.db"))
    yield s
    s.close()


@pytest.fixture
def wired(monkeypatch):
    monkeypatch.setenv("AIMARKET_ESCROW_CONTRACT", _ESCROW)
    monkeypatch.setenv("AIMARKET_ESCROW_HUB_ADDRESS", _HUB)
    monkeypatch.setenv("AIMARKET_ESCROW_MAX_UNCOLLECTED_USD", "5.0")
    state = {"nonce": 0}

    def _read(cid, address=None):
        return chain.EscrowChannel(
            channel_id=_ESCROW_CHANNEL, depositor=_account().address.lower(), hub=_ZERO,
            token=_TOKEN, deposit_amount=5_000_000, balance=5_000_000, used_amount=0,
            expires_at=4_000_000_000, nonce=state["nonce"], status=chain.STATUS_OPEN,
        )

    monkeypatch.setattr(chain, "chain_id", lambda: _CHAIN_ID)
    monkeypatch.setattr(chain, "escrow_address", lambda: _ESCROW)
    monkeypatch.setattr(chain, "read_channel", _read)
    monkeypatch.setattr(chain, "receipt_already_used", lambda *a, **k: False)
    monkeypatch.setattr(chain, "simulate", lambda **k: {"ok": True, "error": "", "gas": 100_000})
    return state


def _payload(*, amount, receipt, nonce=0):
    from eth_account import Account
    from aimarket_hub.escrow_bridge import eip712

    auth = DebitAuthorization(channel_id=_ESCROW_CHANNEL, hub=_HUB, token=_TOKEN, amount=amount,
                              receipt_id=receipt, nonce=nonce, deadline=_DEADLINE)
    digest = eip712.debit_digest(auth, chain_id=_CHAIN_ID, verifying_contract=_ESCROW)
    sig = Account._sign_hash(digest, Account.from_key(_DEPOSITOR_KEY).key).signature.hex()
    return {**auth.as_message(), "signature": sig if sig.startswith("0x") else "0x" + sig}


def _accept(st, payload):
    # Exactly how local_admission calls it: expected_receipt_id is read from the payload.
    return authorization.verify_and_store(
        payload=payload, ledger_channel_id="ch_abc", escrow_channel_id=_ESCROW_CHANNEL,
        expected_amount_usd=1.0, expected_receipt_id=payload["receiptId"], authorizations=st,
        now=_NOW,
    )


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """A real ChannelLedger on a scratch file, with one open channel of $5."""
    from aimarket_hub import channels as ch_mod

    path = str(tmp_path / "channels.db")
    led = ch_mod.ChannelLedger(db_path=path)
    led._running = False
    with sqlite3.connect(path) as c:
        c.execute(
            "INSERT INTO channels (channel_id, balance_cents, original_deposit_cents, used_cents, "
            "wallet, status, opened_at, expires_at, secret_hash) VALUES "
            "('ch_abc', 500, 500, 0, '', 'open', '2026-01-01T00:00:00Z', '2099-01-01T00:00:00Z', ?)",
            (ch_mod._hash_secret("s3cret"),),
        )
    monkeypatch.setattr(ch_mod, "_DB_PATH", path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return led


class _RecordingSigner(signer_mod.Signer):
    name = "recording"

    def __init__(self):
        self.sent = []

    @property
    def sender(self):
        return _HUB

    def submit(self, tx):
        self.sent.append(tx)
        return "0x" + "ee" * 32


def _units_in_calldata(data_hex: str) -> int:
    raw = bytes.fromhex(data_hex[2:])
    return int.from_bytes(raw[4 + 32:4 + 64], "big")


# ── Finding 1: case-variant receiptId resets the running total ───────────────────────────

def test_case_variant_receipt_lets_buyer_pay_one_call_per_window(st, wired, ledger):
    r_lower = "0x" + "ab" * 32
    r_upper = "0x" + "AB" * 32
    r_mixed = "0x" + "Ab" * 32

    # Control: a genuinely different receipt must carry the running total (2P), so P is refused.
    _accept(st, _payload(amount=_P, receipt=r_lower))
    with pytest.raises(AuthorizationRejected, match="running total"):
        _accept(st, _payload(amount=_P, receipt="0x" + "cd" * 32))

    # Attack: the SAME bytes32 with different hex case is treated as "a replay of one call"
    # (carried = 0), so the buyer signs only P — and it supersedes the earlier P.
    _accept(st, _payload(amount=_P, receipt=r_upper))
    _accept(st, _payload(amount=_P, receipt=r_mixed))
    live = st.active_at(_ESCROW_CHANNEL, 0)
    assert live.receipt_id == r_mixed and live.amount_units == _P

    # The ledger keys receipts case-sensitively: three distinct holds+captures = $3 debited.
    for r in (r_lower, r_upper, r_mixed):
        assert ledger.hold("ch_abc", 1.0, receipt_id=r, secret="s3cret").get("ok"), r
        assert ledger.capture_hold(r).get("ok"), r
    with sqlite3.connect(ledger._db_path) as c:
        assert c.execute("SELECT SUM(amount_cents) FROM debited_receipts").fetchone()[0] == 300

    # The mirror collects only P on chain for those three delivered calls.
    signer = _RecordingSigner()
    m = mirror.Mirror(authorizations=st, signer=signer, require_enabled=False)
    m._dry_run = False
    rep = m.run(now=_NOW)
    assert len(signer.sent) == 1, rep.as_dict()
    assert _units_in_calldata(signer.sent[0].data) == _P   # $1 collected for $3 served


# ── Finding 2: withdrawing a superseded call poisons the window ─────────────────────────

def test_withdraw_of_superseded_call_blocks_whole_window(st, wired, ledger):
    ra, rb, rc = "0x" + "a1" * 32, "0x" + "b2" * 32, "0x" + "c3" * 32
    # A: long call, held.  B: concurrent call, must sign A+B = 2P; supersedes A.
    _accept(st, _payload(amount=_P, receipt=ra))
    assert ledger.hold("ch_abc", 1.0, receipt_id=ra, secret="s3cret").get("ok")
    _accept(st, _payload(amount=2 * _P, receipt=rb))
    assert ledger.hold("ch_abc", 1.0, receipt_id=rb, secret="s3cret").get("ok")
    assert ledger.capture_hold(rb).get("ok")          # B delivered and charged
    # A fails: _local_unwind -> withdraw(A) then release_hold(A).
    authorization.withdraw(ra, st, reason="the call was not delivered")
    assert ledger.release_hold(ra).get("ok")
    # withdraw was a no-op (A already abandoned as superseded): B still claims 2P.
    assert st.get(rb).status == store.PENDING and st.get(rb).amount_units == 2 * _P

    signer = _RecordingSigner()
    m = mirror.Mirror(authorizations=st, signer=signer, require_enabled=False)
    m._dry_run = False
    rep = m.run(now=_NOW)
    assert signer.sent == []
    assert "over-collect" in rep.rows[0]["detail"]

    # C: the next call must carry B's poisoned total (3P); it is blocked the same way.
    _accept(st, _payload(amount=3 * _P, receipt=rc))
    assert ledger.hold("ch_abc", 1.0, receipt_id=rc, secret="s3cret").get("ok")
    assert ledger.capture_hold(rc).get("ok")
    rep = m.run(now=_NOW)
    assert signer.sent == [] and "over-collect" in rep.rows[0]["detail"]
    # At the deadline the mirror abandons it: B and C were delivered and charged, $0 collected.
    rep = m.run(now=_DEADLINE + 1)
    assert st.get(rc).status == store.ABANDONED


# ── Finding 3: a reverted (or never-mined) submission is a permanent dead end ───────────

def test_reverted_submission_is_never_retried_and_bricks_channel(st, wired, ledger, monkeypatch):
    r = "0x" + "d4" * 32
    _accept(st, _payload(amount=_P, receipt=r))
    assert ledger.hold("ch_abc", 1.0, receipt_id=r, secret="s3cret").get("ok")
    assert ledger.capture_hold(r).get("ok")
    signer = _RecordingSigner()
    m = mirror.Mirror(authorizations=st, signer=signer, require_enabled=False)
    m._dry_run = False
    m.run(now=_NOW)
    assert st.get(r).status == store.SUBMITTED and len(signer.sent) == 1

    class _Pool:
        def call(self, method, params=None):
            return {"status": "0x0"}  # reverted

    monkeypatch.setattr(chain, "_pool", lambda: _Pool())
    for _ in range(3):
        m.confirm()
        m.run(now=_NOW)  # docstring: "the next pass re-simulates" — it does not
    assert st.get(r).status == store.SUBMITTED
    assert len(signer.sent) == 1   # never re-simulated / re-sent
    # Chain nonce is still 0; every new call on this escrow channel is refused.
    with pytest.raises(AuthorizationRejected):
        _accept(st, _payload(amount=_P, receipt="0x" + "e5" * 32))
    # Even past the deadline nothing resolves it.
    m.confirm(); m.run(now=_DEADLINE + 10)
    assert st.get(r).status == store.SUBMITTED


# ── Finding 4: a Pay-on-Verified capture after the authorization deadline ───────────────

def test_late_pov_capture_is_charged_but_never_collected(st, wired, ledger):
    r = "0x" + "f6" * 32
    _accept(st, _payload(amount=_P, receipt=r))
    assert ledger.hold("ch_abc", 1.0, receipt_id=r, secret="s3cret").get("ok")  # PoV: held
    signer = _RecordingSigner()
    m = mirror.Mirror(authorizations=st, signer=signer, require_enabled=False)
    m._dry_run = False
    m.run(now=_NOW)                       # blocked: ledger has only a hold
    assert st.get(r).status == store.PENDING
    m.run(now=_DEADLINE + 1)              # verifier still out: deadline passes
    assert st.get(r).status == store.ABANDONED
    assert ledger.capture_hold(r).get("ok")   # verdict finally lands: buyer charged
    with sqlite3.connect(ledger._db_path) as c:
        assert c.execute("SELECT amount_cents FROM debited_receipts WHERE receipt_id=?",
                         (r,)).fetchone()[0] == 100
    assert signer.sent == []              # nothing ever collected on chain


# ── Finding 5: the daily cap turns excess served calls into abandoned debits ────────────

def test_daily_cap_blocked_rows_expire_instead_of_waiting(st, wired, ledger, monkeypatch):
    monkeypatch.setenv("AIMARKET_ESCROW_MAX_USD_PER_DAY", "1.0")
    monkeypatch.setenv("AIMARKET_ESCROW_MAX_USD_PER_PASS", "0")
    # Another channel already used today's $1 budget.
    st.record(receipt_id="0x" + "77" * 32, ledger_channel="ch_x", escrow_channel="0x" + "99" * 32,
              chain_id=_CHAIN_ID, escrow_address=_ESCROW, hub=_HUB, token=_TOKEN,
              depositor="0x" + "aa" * 20, amount_units=_P, nonce=0, deadline=_DEADLINE,
              signature="0x" + "ab" * 65)
    st.mark_submitted("0x" + "77" * 32, "0x" + "ee" * 32)
    r = "0x" + "a7" * 32
    _accept(st, _payload(amount=_P, receipt=r))
    assert ledger.hold("ch_abc", 1.0, receipt_id=r, secret="s3cret").get("ok")
    assert ledger.capture_hold(r).get("ok")
    signer = _RecordingSigner()
    m = mirror.Mirror(authorizations=st, signer=signer, require_enabled=False)
    m._dry_run = False
    rep = m.run(now=_NOW)
    assert signer.sent == [] and "daily ceiling" in rep.rows[-1]["detail"]
    m.run(now=_DEADLINE + 1)
    assert st.get(r).status == store.ABANDONED   # served + charged, never collectable
