"""Repro: a debit whose broadcast reverted stays SUBMITTED forever and blocks its escrow channel.

mirror.confirm() says "it will be re-simulated against current state", but run() skips every
SUBMITTED row and _preflight (the only place that abandons or re-simulates) is never reached.
"""
import sys
import time

sys.path.insert(0, "/Users/alex/Desktop/ai_tests/aicompany/aicom/.claude/worktrees/bold-volhard-8c154f/aimarket-hub")

import pytest

from aimarket_hub.escrow_bridge import chain, mirror, store

CH = "0x" + "ab" * 32
ESCROW = "0x" + "11" * 20
HUB = "0x" + "22" * 20
TOKEN = "0x" + "33" * 20
DEP = "0x" + "44" * 20


class FakeSigner:
    name = "fake"
    sender = HUB

    def __init__(self):
        self.sent = []

    def submit(self, tx):
        self.sent.append(tx)
        return "0x" + "ee" * 32


class Pool:
    def call(self, method, params):
        assert method == "eth_getTransactionReceipt"
        return {"status": "0x0"}          # the debit reverted on chain


def _rid(n):
    return "0x" + f"{n:064x}"


@pytest.fixture
def env(monkeypatch):
    sims = []
    monkeypatch.setattr(chain, "receipt_already_used", lambda *a, **k: False)
    monkeypatch.setattr(chain, "encode_debit_channel", lambda auth, sig: "0xdeadbeef")

    def sim(**kw):
        sims.append(kw)
        return {"ok": True, "gas": 100000}

    monkeypatch.setattr(chain, "simulate", sim)
    monkeypatch.setattr(chain, "_pool", lambda: Pool())
    monkeypatch.setattr(mirror, "_ledger_debited_cents", lambda rid: 1)
    st = store.AuthorizationStore(":memory:")
    signer = FakeSigner()
    m = mirror.Mirror(authorizations=st, signer=signer, require_enabled=False)
    return st, m, signer, sims


def test_reverted_submission_never_retried_or_abandoned(env):
    st, m, signer, sims = env
    now = time.time()
    st.record(receipt_id=_rid(1), ledger_channel="ch_x", escrow_channel=CH, chain_id=8453,
              escrow_address=ESCROW, hub=HUB, token=TOKEN, depositor=DEP,
              amount_units=10_000, nonce=0, deadline=int(now) + 7200, signature="0x" + "00" * 65)

    rep = m.run(limit=5, now=now)
    assert rep.outcomes.get("submitted") == 1 and len(signer.sent) == 1

    rep = m.confirm(limit=20)
    assert rep.outcomes.get("blocked") == 1                       # "will be re-simulated"
    assert st.get(_rid(1)).status == store.SUBMITTED

    sims.clear()
    # Many later passes, even after the authorization deadline: nothing re-simulates,
    # nothing resubmits, nothing abandons.
    for _ in range(3):
        m.confirm(limit=20)
        rep = m.run(limit=5, now=now + 10 ** 6)
    assert sims == [] and len(signer.sent) == 1
    assert st.get(_rid(1)).status == store.SUBMITTED
    assert st.stats()["unsubmitted_units"] == 10_000              # sweep never reads "ok" again

    # The chain nonce did not move (the debit reverted), so the next invoke on this escrow
    # channel signs nonce 0 again — and cannot be stored: the SUBMITTED row holds the slot and
    # authorization.verify_and_store only supersedes PENDING/PLANNED rows.
    with pytest.raises(store.StoreError, match="already stored"):
        st.record(receipt_id=_rid(2), ledger_channel="ch_x", escrow_channel=CH, chain_id=8453,
                  escrow_address=ESCROW, hub=HUB, token=TOKEN, depositor=DEP,
                  amount_units=10_000, nonce=0, deadline=int(now) + 7200,
                  signature="0x" + "00" * 65)
    assert st.active_at(CH, 0).status == store.SUBMITTED


def test_five_stuck_rows_starve_every_other_channel_at_sweep_limit(env):
    """The host sweep runs `submit --yes --limit 5`; unresolved() is ORDER BY escrow_channel,
    nonce LIMIT 5 and run() skips SUBMITTED rows, so five stuck rows on low-sorting channels
    stop collection for every other channel on the hub."""
    st, m, signer, sims = env
    now = time.time()
    for i in range(5):
        ch = "0x0" + f"{i:063x}"
        st.record(receipt_id=_rid(100 + i), ledger_channel=f"ch_{i}", escrow_channel=ch,
                  chain_id=8453, escrow_address=ESCROW, hub=HUB, token=TOKEN, depositor=DEP,
                  amount_units=10_000, nonce=0, deadline=int(now) + 7200,
                  signature="0x" + "00" * 65)
        st.mark_submitted(_rid(100 + i), "0x" + f"{i:064x}")
    m.confirm(limit=20)                       # all five reverted: stay SUBMITTED
    healthy = "0xf" + "0" * 63
    st.record(receipt_id=_rid(200), ledger_channel="ch_ok", escrow_channel=healthy,
              chain_id=8453, escrow_address=ESCROW, hub=HUB, token=TOKEN, depositor=DEP,
              amount_units=10_000, nonce=0, deadline=int(now) + 7200,
              signature="0x" + "00" * 65)
    signer.sent.clear()
    rep = m.run(limit=5, now=now)
    assert rep.scanned == 5 and signer.sent == []          # the healthy row is never reached
    assert st.get(_rid(200)).status == store.PENDING
    # ...until its deadline passes; a later pass with a bigger limit can only abandon it.
    rep = m.run(limit=200, now=now + 8000)
    assert st.get(_rid(200)).status == store.ABANDONED


def test_single_window_above_default_pass_cap_is_never_collected(env, monkeypatch):
    """verify_and_store serves the first call of a window "whatever its price"; the mirror's
    default AIMARKET_ESCROW_MAX_USD_PER_PASS=5 then blocks that row on every pass until its
    deadline, and it is abandoned: delivered, never collected."""
    monkeypatch.delenv("AIMARKET_ESCROW_MAX_USD_PER_PASS", raising=False)
    monkeypatch.delenv("AIMARKET_ESCROW_MAX_USD_PER_DAY", raising=False)
    st, m, signer, sims = env
    monkeypatch.setattr(mirror, "_ledger_debited_cents", lambda rid: 600)   # ledger debited $6
    now = time.time()
    st.record(receipt_id=_rid(300), ledger_channel="ch_big", escrow_channel=CH, chain_id=8453,
              escrow_address=ESCROW, hub=HUB, token=TOKEN, depositor=DEP,
              amount_units=6_000_000, nonce=0, deadline=int(now) + 3600,
              signature="0x" + "00" * 65)
    for k in range(4):                         # every 15-minute pass inside the deadline
        rep = m.run(limit=5, now=now + k * 900)
        assert rep.outcomes.get("blocked") == 1 and signer.sent == []
    m.run(limit=5, now=now + 3601)
    assert st.get(_rid(300)).status == store.ABANDONED


def test_refunded_call_inside_a_window_poisons_the_whole_window(env, monkeypatch):
    """Call A (Pay-on-Verified, verdict pending) stores row A; call B on the same escrow channel
    signs the running total A+B and supersedes A (what verify_and_store does for a PENDING live
    row). A's verdict then FAILS: finalizing releases A's hold and calls withdraw(A) — a no-op,
    because A is already ABANDONED/superseded. Row B still claims A+B, the ledger shows only B,
    so guard 2 refuses it on every pass until its deadline: B (and every later call in the
    window) is delivered and never collected."""
    from aimarket_hub.escrow_bridge import authorization as bridge_auth

    st, m, signer, sims = env
    debited = {_rid(401): None, _rid(402): 5}          # A released (no debit), B debited 5c
    monkeypatch.setattr(mirror, "_ledger_debited_cents", lambda rid: debited.get(rid))
    now = time.time()
    kw = dict(ledger_channel="ch_w", escrow_channel=CH, chain_id=8453, escrow_address=ESCROW,
              hub=HUB, token=TOKEN, depositor=DEP, nonce=0, signature="0x" + "00" * 65)
    st.record(receipt_id=_rid(401), amount_units=100_000, deadline=int(now) + 7200, **kw)  # A $0.10
    st.abandon(_rid(401), store.SUPERSEDED_REASON)                                         # B arrives
    st.record(receipt_id=_rid(402), amount_units=150_000, deadline=int(now) + 7200, **kw)  # A+B
    bridge_auth.withdraw(_rid(401), st, reason="refunded: the delivery failed verification")
    assert st.get(_rid(402)).status == store.PENDING      # nothing changed for the window
    for k in range(8):
        rep = m.run(limit=5, now=now + k * 900)
        assert signer.sent == []
        assert "over-collect" in rep.rows[-1]["detail"]
    m.run(limit=5, now=now + 7201)
    assert st.get(_rid(402)).status == store.ABANDONED    # B's 5c (delivered) never collected
