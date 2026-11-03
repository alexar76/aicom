"""C2 — the authorization store's invariants, and the acceptance checks in front of it.

The store is the only thing standing between "the buyer signed one debit" and "the hub
submitted two", so its invariants are tested as rules rather than as happy paths: identity
is the contract's own replay key, transitions are forward-only, and one (channel, nonce)
can hold exactly one authorization.
"""

from __future__ import annotations

import pytest

from aimarket_hub.escrow_bridge import authorization, chain, store
from aimarket_hub.escrow_bridge.eip712 import DebitAuthorization, crypto_available
from aimarket_hub.escrow_bridge.errors import AuthorizationRejected, BridgeConfigError

pytestmark = pytest.mark.skipif(
    not crypto_available(), reason="eth-utils/eth-account not installed (platon venv)"
)

_ESCROW = "0xe7f1725e7734ce288f8367e1bb143e90bb3f0512"
_HUB = "0x70997970c51812dc3a010c7d01b50e0d17dc79c8"
_TOKEN = "0x5fbdb2315678afecb367f032d93f642f64180aa3"
_ESCROW_CHANNEL = "0x" + "11" * 32
_RECEIPT = "0x" + "22" * 32
_CHAIN_ID = 8453
_ZERO = "0x" + "00" * 20
_DEPOSITOR_KEY = "0x" + "42" * 32


@pytest.fixture
def st(tmp_path):
    s = store.AuthorizationStore(str(tmp_path / "bridge.db"))
    yield s
    s.close()


def _record(s, **over):
    args = dict(
        receipt_id=_RECEIPT, ledger_channel="ch_abc", escrow_channel=_ESCROW_CHANNEL,
        chain_id=_CHAIN_ID, escrow_address=_ESCROW, hub=_HUB, token=_TOKEN,
        depositor="0x" + "aa" * 20, amount_units=1_000_000, nonce=0,
        deadline=4_000_000_000, signature="0x" + "ab" * 65,
    )
    args.update(over)
    return s.record(**args)


class TestIdentityAndUniqueness:
    def test_a_receipt_is_stored_once(self, st):
        _record(st)
        with pytest.raises(store.StoreError, match="already stored"):
            _record(st)

    def test_a_second_authorization_for_the_same_nonce_is_refused(self, st):
        """Two rows at one nonce could never both be submitted — the contract takes one."""
        _record(st)
        with pytest.raises(store.StoreError, match="nonce"):
            _record(st, receipt_id="0x" + "33" * 32)

    def test_distinct_nonces_coexist(self, st):
        _record(st)
        _record(st, receipt_id="0x" + "33" * 32, nonce=1)
        assert len(st.unresolved()) == 2

    def test_the_same_nonce_on_another_channel_is_fine(self, st):
        _record(st)
        _record(st, receipt_id="0x" + "33" * 32, escrow_channel="0x" + "99" * 32)
        assert len(st.unresolved()) == 2


class TestForwardOnlyStateMachine:
    def test_the_happy_path(self, st):
        _record(st)
        assert st.get(_RECEIPT).status == store.PENDING
        st.record_plan(_RECEIPT, {"ok": True, "gas": 60000})
        assert st.get(_RECEIPT).status == store.PLANNED
        st.mark_submitted(_RECEIPT, "0xtx")
        assert st.get(_RECEIPT).status == store.SUBMITTED
        row = st.mark_confirmed(_RECEIPT)
        assert row.status == store.CONFIRMED and row.is_terminal and row.resolved_at

    def test_a_confirmed_row_can_never_be_reopened(self, st):
        """Reopening it would let the mirror submit an already-collected debit again."""
        _record(st)
        st.mark_submitted(_RECEIPT, "0xtx")
        st.mark_confirmed(_RECEIPT)
        for move in (
            lambda: st.mark_submitted(_RECEIPT, "0xtx2"),
            lambda: st.abandon(_RECEIPT, "changed my mind"),
            lambda: st.record_plan(_RECEIPT, {"ok": True}),
        ):
            with pytest.raises(store.StoreError, match="forward-only"):
                move()

    def test_an_abandoned_row_stays_abandoned(self, st):
        _record(st)
        st.abandon(_RECEIPT, "deadline passed unrecoverably")
        with pytest.raises(store.StoreError, match="forward-only"):
            st.mark_submitted(_RECEIPT, "0xtx")

    def test_submitted_cannot_walk_back_to_planned(self, st):
        _record(st)
        st.mark_submitted(_RECEIPT, "0xtx")
        # A plan recorded after submission is informational only; the status must hold.
        st.record_plan(_RECEIPT, {"ok": True})
        assert st.get(_RECEIPT).status == store.SUBMITTED

    def test_a_failed_simulation_does_not_demote_the_row(self, st):
        """Most reverts here are transient (an unfilled nonce gap, an unreachable node),
        and demoting would lose the queue position that keeps submissions ordered."""
        _record(st)
        st.record_plan(_RECEIPT, {"ok": True})
        row = st.record_plan(_RECEIPT, {"ok": False, "error": "execution reverted: nonce"})
        assert row.status == store.PLANNED
        assert "nonce" in row.last_error and row.attempts == 2

    def test_transitions_on_an_unknown_receipt_are_refused(self, st):
        with pytest.raises(store.StoreError, match="no authorization"):
            st.mark_submitted("0x" + "ff" * 32, "0xtx")


class TestQueueOrder:
    def test_next_is_the_lowest_unresolved_nonce(self, st):
        for i in (2, 0, 1):
            _record(st, receipt_id="0x" + f"{i:02x}" * 32, nonce=i)
        assert st.next_for_channel(_ESCROW_CHANNEL).nonce == 0

    def test_resolved_rows_leave_the_queue(self, st):
        for i in (0, 1):
            _record(st, receipt_id="0x" + f"{i:02x}" * 32, nonce=i)
        first = "0x" + "00" * 32
        st.mark_submitted(first, "0xtx")
        st.mark_confirmed(first)
        assert st.next_for_channel(_ESCROW_CHANNEL).nonce == 1

    def test_an_unknown_channel_has_no_next(self, st):
        assert st.next_for_channel("0x" + "77" * 32) is None


class TestReportingDoesNotLeak:
    def test_the_signature_is_never_rendered(self, st):
        """It is the buyer's credential for this debit; operator views have no use for it."""
        secret = "0x" + "cd" * 65
        row = _record(st, signature=secret)
        assert secret not in repr(row.as_dict())
        assert row.as_dict()["signature"].startswith("<")

    def test_stats_report_what_is_still_owed(self, st):
        _record(st)
        _record(st, receipt_id="0x" + "33" * 32, nonce=1, amount_units=500_000)
        assert st.stats()["unsubmitted_units"] == 1_500_000
        assert st.stats()["unsubmitted_usd"] == 1.5
        st.mark_submitted(_RECEIPT, "0xtx")
        st.mark_confirmed(_RECEIPT)
        assert st.stats()["unsubmitted_units"] == 500_000


class TestAcceptance:
    """The checks in front of the store: everything the contract will ask, asked early."""

    def _account(self):
        from eth_account import Account

        return Account.from_key(_DEPOSITOR_KEY)

    @pytest.fixture
    def wired(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_ESCROW_CONTRACT", _ESCROW)
        monkeypatch.setenv("AIMARKET_ESCROW_HUB_ADDRESS", _HUB)
        depositor = self._account().address

        def _install(**over):
            state = dict(nonce=0, balance=5_000_000, status=chain.STATUS_OPEN,
                         depositor=depositor, token=_TOKEN, expires_at=4_000_000_000)
            state.update(over)
            ch = chain.EscrowChannel(
                channel_id=_ESCROW_CHANNEL, depositor=state["depositor"], hub=_ZERO,
                token=state["token"], deposit_amount=5_000_000, balance=state["balance"],
                used_amount=0, expires_at=state["expires_at"], nonce=state["nonce"],
                status=state["status"],
            )
            monkeypatch.setattr(chain, "chain_id", lambda: _CHAIN_ID)
            monkeypatch.setattr(chain, "escrow_address", lambda: _ESCROW)
            monkeypatch.setattr(chain, "read_channel", lambda cid, address=None: ch)
            return ch

        return _install

    # One hour past the fixed `now` used below: inside the default max TTL, so the
    # deadline check is exercised by the tests that target it rather than by every test.
    _NOW = 1_000_000
    _DEADLINE = _NOW + 3600

    def _payload(self, *, amount=1_000_000, nonce=0, deadline=_DEADLINE,
                 receipt=_RECEIPT, channel=_ESCROW_CHANNEL, hub=_HUB, token=_TOKEN,
                 signer_key=_DEPOSITOR_KEY, sign_over=None):
        from eth_account import Account

        auth = DebitAuthorization(channel_id=channel, hub=hub, token=token, amount=amount,
                                  receipt_id=receipt, nonce=nonce, deadline=deadline)
        from aimarket_hub.escrow_bridge import eip712

        digest = eip712.debit_digest(
            sign_over or auth, chain_id=_CHAIN_ID, verifying_contract=_ESCROW
        )
        sig = Account._sign_hash(digest, Account.from_key(signer_key).key).signature.hex()
        return {**auth.as_message(), "signature": sig if sig.startswith("0x") else "0x" + sig}

    def _accept(self, st, payload, **over):
        args = dict(
            payload=payload, ledger_channel_id="ch_abc", escrow_channel_id=_ESCROW_CHANNEL,
            expected_amount_usd=1.0, expected_receipt_id=_RECEIPT, authorizations=st,
            now=self._NOW,
        )
        args.update(over)
        return authorization.verify_and_store(**args)

    def test_a_correct_authorization_is_accepted_and_stored(self, st, wired):
        wired()
        out = self._accept(st, self._payload())
        assert out.signer.lower() == self._account().address.lower()
        assert st.get(_RECEIPT).status == store.PENDING
        assert out.row.amount_units == 1_000_000

    def test_snake_case_field_names_are_accepted(self, st, wired):
        """Three SDKs spell these differently; a buyer should not have to care."""
        wired()
        p = self._payload()
        p["channel_id"] = p.pop("channelId")
        p["receipt_id"] = p.pop("receiptId")
        assert self._accept(st, p).row.receipt_id == _RECEIPT

    def test_a_signature_from_another_wallet_is_refused(self, st, wired):
        wired()
        payload = self._payload(signer_key="0x" + "77" * 32)
        with pytest.raises(AuthorizationRejected, match="depositor"):
            self._accept(st, payload)

    def test_an_amount_that_does_not_match_the_debit_is_refused(self, st, wired):
        """Authorising a cent and being served a dollar's work is the attack here."""
        wired()
        with pytest.raises(AuthorizationRejected, match="amount"):
            self._accept(st, self._payload(amount=10_000), expected_amount_usd=1.0)

    def test_an_amount_above_the_escrow_balance_is_refused(self, st, wired):
        wired(balance=500_000)
        with pytest.raises(AuthorizationRejected, match="balance"):
            self._accept(st, self._payload(amount=1_000_000))

    def test_a_receipt_for_another_invoke_is_refused(self, st, wired):
        wired()
        other = "0x" + "44" * 32
        with pytest.raises(AuthorizationRejected, match="receiptId"):
            self._accept(st, self._payload(receipt=other), expected_receipt_id=_RECEIPT)

    def test_a_channel_past_its_onchain_expiry_is_refused_while_status_still_says_open(
        self, st, wired
    ):
        """Status stays Open until someone calls expireChannel. Serving on such a channel
        is serving for free: every debit reverts and expireChannel refunds the balance."""
        wired(expires_at=self._NOW - 60)
        with pytest.raises(AuthorizationRejected, match="expires on chain"):
            self._accept(st, self._payload())
        assert st.get(_RECEIPT) is None

    def test_a_channel_expiring_before_the_sweep_could_collect_is_refused(self, st, wired):
        wired(expires_at=self._NOW + 600)  # inside the default 30-minute margin
        with pytest.raises(AuthorizationRejected, match="expires on chain"):
            self._accept(st, self._payload())

    def test_a_channel_with_time_to_collect_is_served(self, st, wired, monkeypatch):
        wired(expires_at=self._NOW + 600)
        monkeypatch.setenv("AIMARKET_ESCROW_EXPIRY_MARGIN_S", "300")
        assert self._accept(st, self._payload()).row.receipt_id == _RECEIPT

    def test_a_stale_nonce_is_refused(self, st, wired):
        wired(nonce=3)
        with pytest.raises(AuthorizationRejected, match="nonce"):
            self._accept(st, self._payload(nonce=2))

    def test_a_future_nonce_is_refused(self, st, wired):
        """It would sit unsubmittable behind a gap the contract will never skip."""
        wired(nonce=0)
        with pytest.raises(AuthorizationRejected, match="nonce"):
            self._accept(st, self._payload(nonce=1))

    def test_an_authorization_for_another_channel_is_refused(self, st, wired):
        wired()
        with pytest.raises(AuthorizationRejected, match="channelId"):
            self._accept(st, self._payload(channel="0x" + "88" * 32))

    def test_an_authorization_bound_to_another_hub_is_refused(self, st, wired):
        wired()
        with pytest.raises(AuthorizationRejected, match="hub"):
            self._accept(st, self._payload(hub="0x" + "99" * 20))

    def test_a_token_mismatch_is_refused(self, st, wired):
        wired()
        with pytest.raises(AuthorizationRejected, match="token"):
            self._accept(st, self._payload(token="0x" + "cc" * 20))

    def test_an_expired_deadline_is_refused(self, st, wired):
        wired()
        with pytest.raises(AuthorizationRejected, match="deadline"):
            self._accept(st, self._payload(deadline=self._NOW - 1), now=self._NOW)

    def test_an_absurdly_distant_deadline_is_refused(self, st, wired):
        """A deadline caps how long the hub may hold a claim; unbounded is a licence."""
        wired()
        with pytest.raises(AuthorizationRejected, match="deadline"):
            self._accept(st, self._payload(deadline=4_000_000_000), now=1_000)

    def test_a_closed_escrow_channel_is_refused(self, st, wired):
        wired(status=chain.STATUS_SETTLED)
        with pytest.raises(AuthorizationRejected, match="not open"):
            self._accept(st, self._payload())

    def test_a_replay_of_a_stored_receipt_is_refused_as_client_error(self, st, wired):
        wired()
        self._accept(st, self._payload())
        with pytest.raises(AuthorizationRejected, match="already stored"):
            self._accept(st, self._payload())

    @pytest.mark.parametrize("payload", [
        None, "string", 42, {}, {"signature": "0xab"},
        {"channelId": _ESCROW_CHANNEL, "hub": _HUB, "token": _TOKEN, "amount": "abc",
         "receiptId": _RECEIPT, "nonce": 0, "deadline": 1, "signature": "0xab"},
    ])
    def test_malformed_payloads_are_client_errors_not_crashes(self, st, wired, payload):
        wired()
        with pytest.raises(AuthorizationRejected):
            self._accept(st, payload)

    def test_a_missing_hub_address_is_an_operator_error(self, st, wired, monkeypatch):
        """Not guessable: the contract binds the hub into the digest."""
        wired()
        monkeypatch.delenv("AIMARKET_ESCROW_HUB_ADDRESS", raising=False)
        with pytest.raises(BridgeConfigError, match="HUB_ADDRESS"):
            self._accept(st, self._payload())

    def test_a_tampered_amount_after_signing_is_refused(self, st, wired):
        """Sign for 0.10, submit a payload claiming 1.00: the digest no longer recovers."""
        wired()
        honest = DebitAuthorization(
            channel_id=_ESCROW_CHANNEL, hub=_HUB, token=_TOKEN, amount=100_000,
            receipt_id=_RECEIPT, nonce=0, deadline=self._DEADLINE,
        )
        payload = self._payload(amount=1_000_000, sign_over=honest)
        with pytest.raises(AuthorizationRejected, match="depositor|recovered"):
            self._accept(st, payload)


class TestStorePathDefault:
    def test_it_lands_beside_the_channel_ledger(self, monkeypatch, tmp_path):
        monkeypatch.delenv("AIMARKET_ESCROW_BRIDGE_DB_PATH", raising=False)
        from aimarket_hub import channels as ch_mod

        monkeypatch.setattr(ch_mod, "_DB_PATH", str(tmp_path / "sub" / "channels.db"))
        assert store.default_db_path() == str(tmp_path / "sub" / "escrow_bridge.db")

    def test_an_explicit_path_wins(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AIMARKET_ESCROW_BRIDGE_DB_PATH", str(tmp_path / "custom.db"))
        assert store.default_db_path() == str(tmp_path / "custom.db")


class TestOneNonceMustCollectEveryCallInItsWindow(TestAcceptance):
    """The 79 abandoned claims on the live hub, and why they were structural.

    `AIMarketEscrow.debitChannel` signs over the channel's CURRENT `ch.nonce`, read from
    storage, and does `ch.nonce += 1` only when a debit lands. So the nonce does not move
    between on-chain debits, every invoke served in that window must sign the SAME nonce,
    and the contract will accept exactly ONE of those signatures.

    With a per-call amount that makes every invoke but one structurally uncollectable.
    The bridge's response was to abandon the earlier row and keep the newest, which is
    why `escrow_bridge.db` on the production hub holds 86 abandoned authorizations —
    79 of them with `last_error = "replaced by fresh buyer authorization for the same
    on-chain nonce"` — against 27 confirmed: $5.05 delivered and never collected, 76% of
    everything the rail ever captured.

    The fix is the invariant every payment channel uses: the authorization at a nonce is
    CUMULATIVE. One debit at nonce N then collects the whole window, and superseding the
    earlier row loses nothing because the later one covers it.
    """

    _SECOND = "0x" + "44" * 32

    def test_a_second_invoke_must_authorize_the_running_total(self, st, wired):
        wired()
        self._accept(st, self._payload())                      # call 1: $1.00 at nonce 0
        assert st.get(_RECEIPT).amount_units == 1_000_000

        # Call 2 in the same window. The chain nonce is still 0 — nothing has been
        # submitted — so the buyer signs nonce 0 again. Signing only this call's price
        # would strand call 1, so it is refused, and the refusal says what to sign.
        per_call = self._payload(amount=1_000_000, receipt=self._SECOND)
        with pytest.raises(AuthorizationRejected) as refusal:
            self._accept(st, per_call, expected_receipt_id=self._SECOND)
        assert "2000000" in str(refusal.value)

    def test_the_cumulative_authorization_supersedes_and_carries_both_calls(self, st, wired):
        wired()
        self._accept(st, self._payload())
        cumulative = self._payload(amount=2_000_000, receipt=self._SECOND)
        out = self._accept(st, cumulative, expected_receipt_id=self._SECOND)

        assert out.row.amount_units == 2_000_000, "the surviving claim must cover both calls"
        assert st.get(self._SECOND).status == store.PENDING
        assert st.get(_RECEIPT).status == store.ABANDONED
        # The whole window is collectable in the one debit the contract allows.
        assert st.stats()["unsubmitted_units"] == 2_000_000

    def test_a_third_call_keeps_accumulating(self, st, wired):
        wired()
        third = "0x" + "55" * 32
        self._accept(st, self._payload())
        self._accept(st, self._payload(amount=2_000_000, receipt=self._SECOND),
                     expected_receipt_id=self._SECOND)
        out = self._accept(st, self._payload(amount=3_000_000, receipt=third),
                           expected_receipt_id=third)
        assert out.row.amount_units == 3_000_000
        assert st.stats()["unsubmitted_units"] == 3_000_000

    def test_uncollected_service_on_one_channel_is_bounded(self, st, wired, monkeypatch):
        """Live V1 lets the depositor settle or refund before the next debit lands and take
        back everything served since the last one; the hub caps how much it serves on credit
        per channel, so that window is worth at most the cap until a debit confirms."""
        wired()
        monkeypatch.setenv("AIMARKET_ESCROW_MAX_UNCOLLECTED_USD", "2.0")
        third = "0x" + "55" * 32
        self._accept(st, self._payload())                                      # $1 carried
        self._accept(st, self._payload(amount=2_000_000, receipt=self._SECOND),
                     expected_receipt_id=self._SECOND)                         # $2 == cap
        with pytest.raises(AuthorizationRejected, match="uncollected"):
            self._accept(st, self._payload(amount=3_000_000, receipt=third),
                         expected_receipt_id=third)

    def test_the_first_call_of_a_window_is_never_capped(self, st, wired, monkeypatch):
        wired()
        monkeypatch.setenv("AIMARKET_ESCROW_MAX_UNCOLLECTED_USD", "0.5")
        out = self._accept(st, self._payload())                                # $1 > cap, nothing carried
        assert out.row.amount_units == 1_000_000

    def test_a_zero_cap_switches_the_bound_off(self, st, wired, monkeypatch):
        wired()
        monkeypatch.setenv("AIMARKET_ESCROW_MAX_UNCOLLECTED_USD", "0")
        self._accept(st, self._payload())
        out = self._accept(st, self._payload(amount=2_000_000, receipt=self._SECOND),
                           expected_receipt_id=self._SECOND)
        assert out.row.amount_units == 2_000_000

    def test_a_fresh_window_starts_clean_once_the_nonce_advances(self, st, wired):
        """After a debit lands the nonce moves, so the next call is a per-call amount again."""
        wired()
        self._accept(st, self._payload())
        st.mark_submitted(_RECEIPT, "0xtx")
        st.mark_confirmed(_RECEIPT)
        wired(nonce=1)                                          # the chain moved on
        out = self._accept(st, self._payload(amount=1_000_000, nonce=1, receipt=self._SECOND),
                           expected_receipt_id=self._SECOND)
        assert out.row.amount_units == 1_000_000

    def test_a_submitted_claim_is_never_superseded(self, st, wired):
        """A broadcast authorization may still confirm; dropping it would lose it twice."""
        wired()
        self._accept(st, self._payload())
        st.mark_submitted(_RECEIPT, "0xtx")
        with pytest.raises(AuthorizationRejected):
            self._accept(st, self._payload(amount=2_000_000, receipt=self._SECOND),
                         expected_receipt_id=self._SECOND)
        assert st.get(_RECEIPT).status == store.SUBMITTED


class TestAWindowSurvivesACallThatWasNotServed(TestAcceptance):
    """Each call's authorization is stored before the work, as the running total of its
    nonce window, and the row it replaces is abandoned. A call that then fails (provider
    error, refused hold, failed verdict) left the window owing a call nobody delivered:
    the mirror would never collect it, and every later call had to sign it again. Its
    withdrawal now restores the authorization it replaced."""

    _SECOND = "0x" + "44" * 32

    def test_withdrawing_the_newest_call_restores_the_window_before_it(self, st, wired):
        wired()
        self._accept(st, self._payload())                                   # $1, served
        self._accept(st, self._payload(amount=2_000_000, receipt=self._SECOND),
                     expected_receipt_id=self._SECOND)                      # $2 total, fails
        assert st.get(_RECEIPT).status == store.ABANDONED
        authorization.withdraw(self._SECOND, st, reason="the provider failed")
        assert st.get(self._SECOND).status == store.ABANDONED
        assert st.get(_RECEIPT).status == store.PENDING
        assert st.active_at(st.get(_RECEIPT).escrow_channel, 0).receipt_id == _RECEIPT

    def test_withdrawing_the_only_call_leaves_nothing_owed(self, st, wired):
        wired()
        self._accept(st, self._payload())
        authorization.withdraw(_RECEIPT, st, reason="the provider failed")
        assert st.get(_RECEIPT).status == store.ABANDONED
        assert st.active_at(st.get(_RECEIPT).escrow_channel, 0) is None

    def test_a_deadline_the_sweep_cannot_reach_is_refused(self, st, wired, monkeypatch):
        """A buyer-chosen deadline seconds away made every served call uncollectable."""
        wired()
        monkeypatch.setenv("AIMARKET_ESCROW_AUTH_MIN_TTL_S", "1800")
        with pytest.raises(AuthorizationRejected, match="1800"):
            self._accept(st, self._payload(deadline=self._NOW + 60))

    def test_a_non_finite_cap_means_no_cap(self, st, wired, monkeypatch):
        wired()
        monkeypatch.setenv("AIMARKET_ESCROW_MAX_UNCOLLECTED_USD", "inf")
        self._accept(st, self._payload())
        out = self._accept(st, self._payload(amount=2_000_000, receipt=self._SECOND),
                           expected_receipt_id=self._SECOND)
        assert out.row.amount_units == 2_000_000
