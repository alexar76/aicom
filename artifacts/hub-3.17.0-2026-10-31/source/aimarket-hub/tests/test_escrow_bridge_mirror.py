"""C3 — the mirror and its signing strategies.

The single most important assertion in this file is negative: under the shipped defaults,
NOTHING reaches a broadcast. It is enforced with a signer whose submit() fails the test if
it is ever called, so a future refactor that quietly makes the default capable of sending
breaks here rather than on someone's mainnet.

Everything else tests the three guards in front of a submission — queue order, the ledger's
own record, and the contract's simulated verdict — because each one exists to refuse a
specific way of collecting money the hub is not owed.
"""

from __future__ import annotations

import sqlite3

import pytest

from aimarket_hub.escrow_bridge import chain, config, mirror, signer as signer_mod, store
from aimarket_hub.escrow_bridge.eip712 import crypto_available
from aimarket_hub.escrow_bridge.errors import BridgeDisabled, SubmissionRefused

pytestmark = pytest.mark.skipif(
    not crypto_available(), reason="eth-utils/eth-account not installed (platon venv)"
)

_ESCROW = "0xe7f1725e7734ce288f8367e1bb143e90bb3f0512"
_HUB = "0x70997970c51812dc3a010c7d01b50e0d17dc79c8"
_TOKEN = "0x5fbdb2315678afecb367f032d93f642f64180aa3"
_CHANNEL = "0x" + "11" * 32
_RECEIPT = "0x" + "22" * 32
_SIG = "0x" + "ab" * 65
_NOW = 1_000_000


class _ExplodingSigner(signer_mod.Signer):
    """A signer that must never be reached. Named so the failure reads clearly."""

    name = "exploding"

    def submit(self, tx):
        raise AssertionError(
            "the mirror attempted to BROADCAST a transaction under a configuration that "
            "must never broadcast"
        )


class _RecordingSigner(signer_mod.Signer):
    name = "recording"

    def __init__(self, tx_hash="0x" + "ee" * 32, fail=None):
        self.sent: list[signer_mod.UnsignedTx] = []
        self._hash = tx_hash
        self._fail = fail

    @property
    def sender(self):
        return _HUB

    def submit(self, tx):
        if self._fail:
            raise SubmissionRefused(self._fail)
        self.sent.append(tx)
        return self._hash


@pytest.fixture
def st(tmp_path):
    s = store.AuthorizationStore(str(tmp_path / "bridge.db"))
    yield s
    s.close()


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """A stand-in channel ledger DB holding the debit the hub actually recorded."""
    path = tmp_path / "channels.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE debited_receipts (receipt_id TEXT PRIMARY KEY, channel_id TEXT, "
        "amount_cents INTEGER, timestamp TEXT)"
    )
    conn.commit()
    conn.close()
    from aimarket_hub import channels as ch_mod

    monkeypatch.setattr(ch_mod, "_DB_PATH", str(path))

    def _debit(receipt_id=_RECEIPT, cents=100):
        c = sqlite3.connect(path)
        c.execute(
            "INSERT OR REPLACE INTO debited_receipts VALUES (?, ?, ?, '')",
            (receipt_id, "ch_abc", cents),
        )
        c.commit()
        c.close()

    return _debit


@pytest.fixture(autouse=True)
def replay_flag(monkeypatch):
    """Guard 0 reads the contract's ``usedReceipts`` flag, so every test must control it.

    Autouse and defaulting to "not collected": without it each test would reach for a real
    Base RPC and the guard would refuse the row before any of the assertions below could
    run. Mutate ``state["used"]`` (or set ``state["raise"]``) to exercise guard 0 itself.
    """
    state: dict[str, object] = {"used": False, "raise": None}

    def _used(receipt_id, *, address=None, channel_id=None):
        if state["raise"] is not None:
            raise state["raise"]
        used = state["used"]
        return receipt_id in used if isinstance(used, (set, frozenset)) else bool(used)

    monkeypatch.setattr(chain, "receipt_already_used", _used)
    return state


@pytest.fixture
def sim(monkeypatch):
    """Control what the simulated contract says."""
    state = {"ok": True, "error": "", "gas": 60_000}

    def _simulate(*, to, data, sender):
        return dict(state)

    monkeypatch.setattr(chain, "simulate", _simulate)
    return state


def _row(st, **over):
    args = dict(
        receipt_id=_RECEIPT, ledger_channel="ch_abc", escrow_channel=_CHANNEL,
        chain_id=8453, escrow_address=_ESCROW, hub=_HUB, token=_TOKEN,
        depositor="0x" + "aa" * 20, amount_units=1_000_000, nonce=0,
        deadline=_NOW + 3600, signature=_SIG,
    )
    args.update(over)
    return st.record(**args)


def _mirror(st, signer, **kw):
    return mirror.Mirror(authorizations=st, signer=signer, require_enabled=False, **kw)


class TestTheDefaultCannotBroadcast:
    def test_plan_only_is_the_default_signer(self, monkeypatch):
        for var in ("AIMARKET_ESCROW_SUBMIT_STRATEGY", "AIMARKET_ESCROW_SUBMIT_CONFIRM",
                    "AIMARKET_ESCROW_PRIVATE_KEY", "AIMARKET_ESCROW_SIGNER_URL"):
            monkeypatch.delenv(var, raising=False)
        assert isinstance(signer_mod.build_signer(), signer_mod.PlanOnlySigner)

    def test_a_full_pass_under_defaults_never_reaches_a_signer(self, st, ledger, sim):
        """The load-bearing negative test of the whole bridge."""
        ledger(cents=100)
        _row(st)
        report = _mirror(st, _ExplodingSigner.__new__(_ExplodingSigner)).run(now=_NOW)
        # The exploding signer would have raised; getting here means submit() was not called.
        assert report.outcomes.get(mirror.OUTCOME_SUBMITTED, 0) == 0

    def test_plan_mode_still_does_the_useful_work(self, st, ledger, sim):
        """Plan mode proves the authorization WOULD be accepted, and says the gas cost."""
        ledger(cents=100)
        _row(st)
        report = _mirror(st, signer_mod.PlanOnlySigner()).run(now=_NOW)
        assert report.dry_run is True
        assert report.outcomes == {mirror.OUTCOME_PLANNED: 1}
        assert report.rows[0]["gas"] == 60_000
        assert st.get(_RECEIPT).status == store.PLANNED

    def test_an_under_configured_strategy_degrades_to_plan(self, monkeypatch):
        """Naming a strategy is not enough; the confirmation phrase is a second act."""
        monkeypatch.setenv("AIMARKET_ESCROW_SUBMIT_STRATEGY", "external")
        monkeypatch.setenv("AIMARKET_ESCROW_SIGNER_URL", "https://signer.invalid")
        monkeypatch.delenv("AIMARKET_ESCROW_SUBMIT_CONFIRM", raising=False)
        assert isinstance(signer_mod.build_signer(), signer_mod.PlanOnlySigner)

    def test_a_fully_configured_strategy_is_honoured(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_ESCROW_SUBMIT_STRATEGY", "external")
        monkeypatch.setenv("AIMARKET_ESCROW_SIGNER_URL", "https://signer.invalid")
        monkeypatch.setenv("AIMARKET_ESCROW_SUBMIT_CONFIRM", config.SUBMIT_CONFIRM_PHRASE)
        assert isinstance(signer_mod.build_signer(), signer_mod.ExternalSigner)

    def test_the_mirror_refuses_to_run_when_the_bridge_is_off(self, monkeypatch, st):
        monkeypatch.delenv("AIMARKET_ESCROW_BRIDGE_ENABLED", raising=False)
        with pytest.raises(BridgeDisabled):
            mirror.Mirror(authorizations=st, signer=signer_mod.PlanOnlySigner())


class TestNonceOrder:
    def test_a_later_nonce_waits_behind_an_earlier_one(self, st, ledger, sim):
        """The contract only accepts the current nonce, so skipping would strand a row."""
        ledger(receipt_id="0x" + "01" * 32, cents=100)
        ledger(receipt_id="0x" + "02" * 32, cents=100)
        _row(st, receipt_id="0x" + "01" * 32, nonce=0)
        _row(st, receipt_id="0x" + "02" * 32, nonce=1)
        report = _mirror(st, _RecordingSigner()).run(now=_NOW)
        by_receipt = {r["receipt_id"]: r for r in report.rows}
        assert by_receipt["0x" + "01" * 32]["outcome"] == mirror.OUTCOME_SUBMITTED
        assert by_receipt["0x" + "02" * 32]["outcome"] == mirror.OUTCOME_BLOCKED
        assert "waiting behind nonce 0" in by_receipt["0x" + "02" * 32]["detail"]

    def test_the_queue_advances_once_the_earlier_row_resolves(self, st, ledger, sim):
        ledger(receipt_id="0x" + "01" * 32, cents=100)
        ledger(receipt_id="0x" + "02" * 32, cents=100)
        first = _row(st, receipt_id="0x" + "01" * 32, nonce=0)
        _row(st, receipt_id="0x" + "02" * 32, nonce=1)
        st.mark_submitted(first.receipt_id, "0xtx")
        st.mark_confirmed(first.receipt_id)
        rec = _RecordingSigner()
        report = _mirror(st, rec).run(now=_NOW)
        assert report.outcomes.get(mirror.OUTCOME_SUBMITTED) == 1
        assert len(rec.sent) == 1

    def test_an_already_submitted_row_is_not_resubmitted(self, st, ledger, sim):
        """Re-broadcasting only spends gas to hit the contract's own replay guard."""
        ledger(cents=100)
        _row(st)
        st.mark_submitted(_RECEIPT, "0xtx")
        rec = _RecordingSigner()
        _mirror(st, rec).run(now=_NOW)
        assert rec.sent == []


class TestTheLedgerGuard:
    def test_a_receipt_the_ledger_never_debited_is_refused(self, st, ledger, sim):
        """The hub must be able to show it charged for what it collects."""
        _row(st)                     # no ledger row for it
        report = _mirror(st, _RecordingSigner()).run(now=_NOW)
        assert report.outcomes == {mirror.OUTCOME_BLOCKED: 1}
        assert "no debit for this receipt" in report.rows[0]["detail"]

    def test_collecting_more_than_the_ledger_debited_is_refused(self, st, ledger, sim):
        """Guards against a hub bug or a tampered store over-collecting on chain."""
        ledger(cents=10)             # $0.10 charged off chain
        _row(st, amount_units=1_000_000)   # $1.00 signed
        report = _mirror(st, _RecordingSigner()).run(now=_NOW)
        assert report.outcomes == {mirror.OUTCOME_BLOCKED: 1}
        assert "over-collect" in report.rows[0]["detail"]

    def test_collecting_less_than_the_ledger_debited_is_allowed(self, st, ledger, sim):
        """Under-collecting only costs the hub, so it is not the bridge's job to refuse."""
        ledger(cents=100)
        _row(st, amount_units=500_000)
        report = _mirror(st, _RecordingSigner()).run(now=_NOW)
        assert report.outcomes.get(mirror.OUTCOME_SUBMITTED) == 1

    def test_an_unreadable_ledger_blocks_rather_than_assumes(self, st, sim, monkeypatch):
        from aimarket_hub import channels as ch_mod

        monkeypatch.setattr(ch_mod, "_DB_PATH", "/nonexistent/channels.db")
        _row(st)
        report = _mirror(st, _RecordingSigner()).run(now=_NOW)
        assert report.outcomes == {mirror.OUTCOME_BLOCKED: 1}


class TestSimulationGuard:
    def test_a_reverting_simulation_blocks_and_is_recorded(self, st, ledger, sim):
        ledger(cents=100)
        _row(st)
        sim.update(ok=False, error="execution reverted: ReceiptAlreadyUsed", gas=None)
        report = _mirror(st, _RecordingSigner()).run(now=_NOW)
        assert report.outcomes == {mirror.OUTCOME_BLOCKED: 1}
        row = st.get(_RECEIPT)
        assert "ReceiptAlreadyUsed" in row.last_error
        # A revert is usually transient here, so the row keeps its queue position.
        assert row.status == store.PENDING

    def test_a_passed_deadline_is_abandoned_not_retried_forever(self, st, ledger, sim):
        """The signature can never be submitted again, so the debit is uncollectable."""
        ledger(cents=100)
        _row(st, deadline=_NOW - 1)
        report = _mirror(st, _RecordingSigner()).run(now=_NOW)
        assert report.outcomes == {mirror.OUTCOME_REJECTED: 1}
        assert st.get(_RECEIPT).status == store.ABANDONED

    def test_gas_is_padded_above_the_estimate(self, st, ledger, sim):
        """State can shift between estimate and inclusion; a tight limit reverts."""
        ledger(cents=100)
        _row(st)
        rec = _RecordingSigner()
        _mirror(st, rec).run(now=_NOW)
        assert rec.sent[0].gas > 60_000


class TestSubmissionAndConfirmation:
    def test_a_refusal_leaves_the_row_retryable(self, st, ledger, sim):
        ledger(cents=100)
        _row(st)
        report = _mirror(st, _RecordingSigner(fail="signer offline")).run(now=_NOW)
        assert report.outcomes == {mirror.OUTCOME_REFUSED: 1}
        assert st.get(_RECEIPT).status == store.PLANNED   # not terminal, retryable

    def test_confirmation_reads_the_chain_not_the_signer(self, st, ledger, sim, monkeypatch):
        """A signer that claims success proves nothing; a receipt does."""
        ledger(cents=100)
        _row(st)
        _mirror(st, _RecordingSigner()).run(now=_NOW)
        assert st.get(_RECEIPT).status == store.SUBMITTED

        class _Pool:
            def call(self, method, params=None):
                assert method == "eth_getTransactionReceipt"
                return {"status": "0x1"}

        monkeypatch.setattr(chain, "_pool", lambda: _Pool())
        report = _mirror(st, _RecordingSigner()).confirm()
        assert report.outcomes == {mirror.OUTCOME_CONFIRMED: 1}
        assert st.get(_RECEIPT).status == store.CONFIRMED

    def test_an_unmined_transaction_stays_submitted(self, st, ledger, sim, monkeypatch):
        ledger(cents=100)
        _row(st)
        _mirror(st, _RecordingSigner()).run(now=_NOW)

        class _Pool:
            def call(self, method, params=None):
                return None

        monkeypatch.setattr(chain, "_pool", lambda: _Pool())
        report = _mirror(st, _RecordingSigner()).confirm()
        assert report.outcomes == {mirror.OUTCOME_BLOCKED: 1}
        assert st.get(_RECEIPT).status == store.SUBMITTED

    def test_a_reverted_receipt_is_not_terminal(self, st, ledger, sim, monkeypatch):
        """Usually a nonce the chain moved past — re-simulate, do not discard a valid sig."""
        ledger(cents=100)
        _row(st)
        _mirror(st, _RecordingSigner()).run(now=_NOW)

        class _Pool:
            def call(self, method, params=None):
                return {"status": "0x0"}

        monkeypatch.setattr(chain, "_pool", lambda: _Pool())
        _mirror(st, _RecordingSigner()).confirm()
        row = st.get(_RECEIPT)
        assert row.status == store.SUBMITTED and "reverted" in row.last_error


class TestSignerStrategies:
    def test_plan_only_explains_itself(self):
        with pytest.raises(SubmissionRefused, match="NOT sent"):
            signer_mod.PlanOnlySigner().submit(
                signer_mod.UnsignedTx(to=_ESCROW, data="0x", chain_id=1, gas=1)
            )

    def test_external_without_a_url_refuses(self):
        with pytest.raises(SubmissionRefused, match="SIGNER_URL"):
            signer_mod.ExternalSigner(url="").submit(
                signer_mod.UnsignedTx(to=_ESCROW, data="0x", chain_id=1, gas=1)
            )

    def test_external_rejects_a_response_without_a_hash(self, monkeypatch):
        """A signer that answers but reports nothing usable must not look like success."""
        import io
        import urllib.request

        class _Ctx(io.BytesIO):
            """urlopen's context-manager shape, with a body that parses but says nothing."""

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(signer_mod, "_open_signer", lambda *a, **k: _Ctx(b'{"ok": true}'))
        with pytest.raises(SubmissionRefused, match="did not return a transaction hash"):
            signer_mod.ExternalSigner(url="https://signer.invalid").submit(
                signer_mod.UnsignedTx(to=_ESCROW, data="0x", chain_id=1, gas=1)
            )

    def test_external_never_sends_the_key_because_it_has_none(self):
        s = signer_mod.ExternalSigner(url="https://signer.invalid", token="tok")
        assert not hasattr(s, "_key")

    def test_env_without_a_key_refuses(self):
        with pytest.raises(SubmissionRefused, match="PRIVATE_KEY"):
            signer_mod.EnvKeySigner(key="").submit(
                signer_mod.UnsignedTx(to=_ESCROW, data="0x", chain_id=1, gas=1)
            )

    def test_env_refuses_a_key_that_is_committed_to_the_repository(self, monkeypatch):
        """A committed key is already public; using it anyway makes hub funds spendable."""
        signer = signer_mod.EnvKeySigner(key="0x" + "42" * 32)

        class _Found:
            returncode = 0

        monkeypatch.setattr(signer_mod.subprocess, "run", lambda *a, **k: _Found())
        with pytest.raises(SubmissionRefused, match="found in the repository"):
            signer.submit(signer_mod.UnsignedTx(to=_ESCROW, data="0x", chain_id=1, gas=1))

    def test_a_missing_git_does_not_silently_pass_or_hard_fail(self, monkeypatch, caplog):
        """Cannot check ≠ safe, but refusing would break a legitimate container deploy."""
        signer = signer_mod.EnvKeySigner(key="0x" + "42" * 32)

        def _boom(*a, **k):
            raise FileNotFoundError("git")

        monkeypatch.setattr(signer_mod.subprocess, "run", _boom)
        with caplog.at_level("WARNING"):
            signer._guard_committed_key()
        assert "not in version control" in caplog.text

    def test_the_key_never_reaches_a_child_process_argv(self, monkeypatch):
        """A guard against a key being public must not be the thing that publishes it.

        Until 2026-07-30 the pattern was ``git grep … <key>`` — the key as argv[4]. On Linux
        ``/proc/<pid>/cmdline`` is world-readable and on any Unix ``ps -ax -o args=`` shows it,
        so for the lifetime of the child every local process could read the hub's escrow key.
        Demonstrated both ways: a child holding a 64-hex secret in argv is visible to an
        unprivileged ps; the same child reading it from stdin is not.
        """
        key = "0x" + "42" * 32
        signer = signer_mod.EnvKeySigner(key=key)
        seen: list[tuple] = []

        def _record(argv, *a, **kw):
            seen.append((tuple(argv), kw.get("input")))
            return type("R", (), {"returncode": 1, "stdout": "", "stderr": b""})()

        monkeypatch.setattr(signer_mod.subprocess, "run", _record)
        signer._guard_committed_key()

        assert seen, "the guard did not run"
        for argv, stdin in seen:
            flat = " ".join(str(part) for part in argv)
            assert "42" * 32 not in flat, f"the key is in argv: {flat}"
        grep = [(argv, stdin) for argv, stdin in seen if "grep" in argv]
        assert grep, seen
        argv, stdin = grep[0]
        assert "-f" in argv and "-" in argv, f"the pattern must come from stdin: {argv}"
        assert stdin == b"42" * 32, "the pattern must actually be sent on stdin"

    def test_the_search_runs_from_the_repository_root(self, monkeypatch):
        """``git grep`` searches downward from where it is invoked.

        The hub is started in its own package directory, so a search from the process's cwd
        could not see a key committed elsewhere in the monorepo while still reporting a clean
        result. A key committed ANYWHERE is public, which is the premise of the whole guard.
        """
        signer = signer_mod.EnvKeySigner(key="0x" + "42" * 32)
        calls: list[dict] = []

        def _run(argv, *a, **kw):
            calls.append({"argv": tuple(argv), "cwd": kw.get("cwd")})
            if "rev-parse" in argv:
                return type("R", (), {"returncode": 0, "stdout": "/repo/root\n", "stderr": ""})()
            return type("R", (), {"returncode": 1, "stdout": "", "stderr": b""})()

        monkeypatch.setattr(signer_mod.subprocess, "run", _run)
        signer._guard_committed_key()

        grep = next(c for c in calls if "grep" in c["argv"])
        assert grep["cwd"] == "/repo/root", grep

    def test_a_git_error_that_is_not_a_miss_warns_rather_than_passing(self, monkeypatch, caplog):
        """Exit 1 is "no match". 128 means the search never happened.

        Both used to reach the same silent success, so running the hub outside a repository
        turned the guard off without saying so.
        """
        signer = signer_mod.EnvKeySigner(key="0x" + "42" * 32)

        def _run(argv, *a, **kw):
            if "rev-parse" in argv:
                return type("R", (), {"returncode": 128, "stdout": "", "stderr": ""})()
            return type("R", (), {"returncode": 128, "stdout": "", "stderr": b"not a git repo"})()

        monkeypatch.setattr(signer_mod.subprocess, "run", _run)
        with caplog.at_level("WARNING"):
            signer._guard_committed_key()
        assert "did not run" in caplog.text
        assert "git exited 128" in caplog.text
        assert "42" * 32 not in caplog.text, "the warning must not echo the key"

    def test_a_clean_miss_stays_silent(self, monkeypatch, caplog):
        """Exit 1 is the normal, good outcome. It must not warn, or the warning means nothing."""
        signer = signer_mod.EnvKeySigner(key="0x" + "42" * 32)
        monkeypatch.setattr(
            signer_mod.subprocess, "run",
            lambda argv, *a, **kw: type("R", (), {
                "returncode": 0 if "rev-parse" in argv else 1,
                "stdout": "/repo\n" if "rev-parse" in argv else "", "stderr": b"",
            })(),
        )
        with caplog.at_level("WARNING"):
            signer._guard_committed_key()
        assert caplog.text == "", caplog.text

    def test_a_signing_error_never_echoes_the_payload(self, monkeypatch):
        """A signing exception can carry the transaction, which sits next to the key."""
        signer = signer_mod.EnvKeySigner(key="0x" + "42" * 32)
        monkeypatch.setattr(signer_mod.subprocess, "run",
                           lambda *a, **k: type("R", (), {"returncode": 1})())

        class _Pool:
            def call(self, method, params=None):
                return "0x1"

        import eth_account

        monkeypatch.setattr(
            eth_account.Account, "sign_transaction",
            staticmethod(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret-ish 0x4242"))),
        )
        signer._pool = _Pool()
        with pytest.raises(SubmissionRefused) as err:
            signer.submit(signer_mod.UnsignedTx(to=_ESCROW, data="0xdead", chain_id=1, gas=1))
        assert "0x4242" not in str(err.value) and "RuntimeError" in str(err.value)


class TestStatusReport:
    def test_status_reports_configuration_and_debt_without_secrets(self, st, monkeypatch):
        monkeypatch.setenv("AIMARKET_ESCROW_PRIVATE_KEY", "0x" + "ab" * 32)
        _row(st)
        out = _mirror(st, signer_mod.PlanOnlySigner()).status()
        assert out["dry_run"] is True
        assert out["store"]["unsubmitted_usd"] == 1.0
        assert "ab" * 32 not in repr(out)


class TestGuardZeroAlreadyCollected:
    """A receipt the contract already counts as used must RESOLVE, never block or abandon.

    Production, 2026-07-29: the store held three rows at ``pending`` with an empty tx hash,
    two of whose receipt ids had already been debited on Base by the operator's own hand.
    Nothing could clear them — ``_ALLOWED`` had no pending→confirmed edge — and because
    submission is strictly nonce-ordered, the first stuck row blocked every later row on its
    channel permanently. The hub was reporting $0.24 owed on money it had already been paid.
    """

    def test_a_collected_receipt_is_confirmed_not_resubmitted(self, st, sim, ledger, replay_flag):
        ledger(_RECEIPT, 100)
        _row(st)
        replay_flag["used"] = True
        signer = _ExplodingSigner()          # fails the test if anything is broadcast
        report = _mirror(st, signer).run(now=_NOW)

        row = st.get(_RECEIPT)
        assert row.status == store.CONFIRMED, "the money is in; confirmed is the truth"
        assert row.is_terminal, "it must stop being retried"
        assert row.tx_hash == "", "the hub does not know which tx did it and must not invent one"
        assert "did not send" in row.last_error, "an operator must be able to see why"
        assert any(n["outcome"] == mirror.OUTCOME_CONFIRMED for n in report.rows)

    def test_it_resolves_even_past_the_deadline(self, st, sim, ledger, replay_flag):
        """Ordering guard: collected-then-expired is paid, not uncollectable.

        The deadline guard abandons a row, which asserts the hub has NO on-chain claim to
        that money. For a receipt the contract already collected that is precisely backwards,
        so guard 0 has to run first.
        """
        ledger(_RECEIPT, 100)
        _row(st, deadline=_NOW - 1)
        replay_flag["used"] = True
        _mirror(st, _ExplodingSigner()).run(now=_NOW)
        assert st.get(_RECEIPT).status == store.CONFIRMED, "abandoning it would deny a paid debit"

    def test_a_collected_head_stops_blocking_the_queue(self, st, sim, ledger, replay_flag):
        """The head-of-line failure itself: clearing nonce 0 must free nonce 1."""
        second = "0x" + "33" * 32
        ledger(_RECEIPT, 100)
        ledger(second, 100)
        _row(st, nonce=0)
        _row(st, receipt_id=second, nonce=1)
        replay_flag["used"] = {_RECEIPT}      # only the head was collected out of band

        signer = _RecordingSigner()
        report = _mirror(st, signer).run(now=_NOW)

        assert st.get(_RECEIPT).status == store.CONFIRMED
        assert st.get(second).status == store.SUBMITTED, (
            "with the head resolved, the next nonce must go out in the same pass"
        )
        assert len(signer.sent) == 1, "exactly the unpaid one"
        assert not any(
            n["outcome"] == mirror.OUTCOME_BLOCKED for n in report.rows
        ), f"nothing should be blocked any more: {report.rows}"

    def test_an_unreadable_flag_blocks_rather_than_assumes_unpaid(self, st, sim, ledger, replay_flag):
        """A read failure is not evidence of "not yet collected".

        Treating it as False would send a debit the contract is guaranteed to reject with
        ReceiptAlreadyUsed, burning gas and leaving the row wrong either way.
        """
        ledger(_RECEIPT, 100)
        _row(st)
        replay_flag["raise"] = RuntimeError("rpc down")
        report = _mirror(st, _ExplodingSigner()).run(now=_NOW)

        assert st.get(_RECEIPT).status == store.PENDING, "unchanged — nothing was learned"
        note = next(n for n in report.rows if n["receipt_id"] == _RECEIPT)
        assert note["outcome"] == mirror.OUTCOME_BLOCKED
        assert "replay flag" in note["detail"]

    def test_confirmed_stays_terminal(self, st, sim, ledger, replay_flag):
        """The relaxed transition table must not let a settled debit be collected twice."""
        ledger(_RECEIPT, 100)
        _row(st)
        replay_flag["used"] = True
        _mirror(st, _ExplodingSigner()).run(now=_NOW)
        assert st.get(_RECEIPT).status == store.CONFIRMED
        with pytest.raises(Exception):
            st.mark_submitted(_RECEIPT, "0x" + "cd" * 32)


class TestSpendBounds:
    """KI-11 asked for a BOUNDED hot wallet. Before this there was no bound of any kind.

    Neither ceiling stops someone holding the key. What they stop is the hub acting on a
    mistake at full speed — a ledger bug, a tampered store, or a long unattended backlog all
    had the same unlimited blast radius when one pass would submit everything it could reach.
    """

    def _rows(self, st, ledger, n, *, units=1_000_000):
        """n independent channels, so nonce order never masks a budget refusal."""
        ids = []
        for i in range(n):
            rid = "0x" + f"{i:02x}" * 32
            ledger(rid, 100)
            _row(st, receipt_id=rid, escrow_channel="0x" + f"{i + 0x40:02x}" * 32,
                 nonce=0, amount_units=units)
            ids.append(rid)
        return ids

    def test_the_per_pass_ceiling_stops_the_pass(self, st, sim, ledger, monkeypatch):
        """$1 rows against a $2.50 ceiling: two go, the third does not."""
        monkeypatch.setenv("AIMARKET_ESCROW_MAX_USD_PER_PASS", "2.50")
        monkeypatch.setenv("AIMARKET_ESCROW_MAX_USD_PER_DAY", "0")   # isolate the pass cap
        self._rows(st, ledger, 3)
        signer = _RecordingSigner()
        report = _mirror(st, signer).run(now=_NOW)

        assert len(signer.sent) == 2, f"sent {len(signer.sent)}, ceiling allows 2"
        blocked = [r for r in report.rows if r["outcome"] == mirror.OUTCOME_BLOCKED]
        assert len(blocked) == 1
        assert "per-pass ceiling" in blocked[0]["detail"]

    def test_the_daily_ceiling_survives_separate_passes(self, st, sim, ledger, monkeypatch):
        """The per-pass cap alone is defeated by running passes back to back.

        Which is exactly what an unattended timer does, so the daily figure is read from the
        store's own record of what was broadcast rather than counted in memory.
        """
        monkeypatch.setenv("AIMARKET_ESCROW_MAX_USD_PER_PASS", "0")   # isolate the daily cap
        monkeypatch.setenv("AIMARKET_ESCROW_MAX_USD_PER_DAY", "2.50")
        ids = self._rows(st, ledger, 3)

        first = _RecordingSigner()
        _mirror(st, first).run(now=_NOW)
        assert len(first.sent) == 2, "the daily cap must bite inside the first pass too"

        # A fresh Mirror: per-pass state is gone, the daily figure is not.
        second = _RecordingSigner(tx_hash="0x" + "dd" * 32)
        report = _mirror(st, second).run(now=_NOW)
        assert second.sent == [], "a second pass must not top up past the daily ceiling"
        assert any("daily ceiling" in r["detail"] for r in report.rows), report.rows
        assert st.get(ids[2]).status != store.SUBMITTED

    def test_externally_collected_debits_do_not_consume_the_budget(self, st, sim, ledger, replay_flag, monkeypatch):
        """A debit the hub did not send cost the hub nothing, so it must not throttle it.

        Otherwise someone else's transaction eats this hub's daily allowance.
        """
        monkeypatch.setenv("AIMARKET_ESCROW_MAX_USD_PER_PASS", "0")
        monkeypatch.setenv("AIMARKET_ESCROW_MAX_USD_PER_DAY", "1.50")
        ids = self._rows(st, ledger, 2)
        replay_flag["used"] = {ids[0]}          # the first was collected out of band

        signer = _RecordingSigner()
        _mirror(st, signer).run(now=_NOW)

        assert st.get(ids[0]).status == store.CONFIRMED
        assert len(signer.sent) == 1, (
            "the externally-collected $1 must not count against the $1.50 daily cap"
        )
        assert st.get(ids[1]).status == store.SUBMITTED

    def test_an_old_submission_falls_out_of_the_rolling_window(self, st, sim, ledger, monkeypatch):
        """The window is wall-clock, because that is what `submitted_at` is stamped with.

        So this backdates the STORE's clock for the first submission rather than advancing
        the mirror's `now` — passing an artificial `now` would compare two different scales,
        which is exactly the coupling `_budget_blocks` avoids. Only the FIRST row exists
        during the backdated pass, or the second would be stamped 25h ago as well and there
        would be nothing left to prove.
        """
        import time as _time

        monkeypatch.setenv("AIMARKET_ESCROW_MAX_USD_PER_PASS", "0")
        monkeypatch.setenv("AIMARKET_ESCROW_MAX_USD_PER_DAY", "1.50")

        old_id = "0x" + "a1" * 32
        ledger(old_id, 100)
        _row(st, receipt_id=old_id, escrow_channel="0x" + "b1" * 32, nonce=0,
             amount_units=1_000_000)

        long_ago = _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime(_time.time() - 25 * 3600))
        real_now = store._now
        # Restored by hand, NOT with monkeypatch.undo(): `monkeypatch` is one shared
        # instance per test, so undo() would also revert the `sim` and `replay_flag`
        # fixtures' patches and send guard 0 at a real RPC.
        store._now = lambda: long_ago
        try:
            _mirror(st, _RecordingSigner()).run(now=_NOW)
        finally:
            store._now = real_now

        assert st.get(old_id).status == store.SUBMITTED
        assert st.get(old_id).submitted_at == long_ago
        assert st.units_collected_since(_time.time() - 86_400) == 0, (
            "the backdated spend must already be outside the 24h window"
        )

        # A fresh row now: the $1 spent 25h ago must not count against the $1.50 ceiling.
        new_id = "0x" + "a2" * 32
        ledger(new_id, 100)
        _row(st, receipt_id=new_id, escrow_channel="0x" + "b2" * 32, nonce=0,
             amount_units=1_000_000)
        signer = _RecordingSigner(tx_hash="0x" + "dd" * 32)
        _mirror(st, signer).run(now=_NOW)
        assert len(signer.sent) == 1, "a 25h-old spend must not throttle forever"

    def test_zero_disables_a_ceiling(self, st, sim, ledger, monkeypatch):
        monkeypatch.setenv("AIMARKET_ESCROW_MAX_USD_PER_PASS", "0")
        monkeypatch.setenv("AIMARKET_ESCROW_MAX_USD_PER_DAY", "0")
        self._rows(st, ledger, 3)
        signer = _RecordingSigner()
        _mirror(st, signer).run(now=_NOW)
        assert len(signer.sent) == 3

    def test_a_refused_submission_does_not_spend_the_budget(self, st, sim, ledger, monkeypatch):
        """A signer refusal moves no money, so it must not consume the pass allowance."""
        monkeypatch.setenv("AIMARKET_ESCROW_MAX_USD_PER_PASS", "1.50")
        monkeypatch.setenv("AIMARKET_ESCROW_MAX_USD_PER_DAY", "0")
        self._rows(st, ledger, 2)
        report = _mirror(st, _RecordingSigner(fail="signer offline")).run(now=_NOW)
        refused = [r for r in report.rows if r["outcome"] == mirror.OUTCOME_REFUSED]
        assert len(refused) == 2, (
            "both must reach the signer: the first spent nothing, so the second is still "
            f"inside the ceiling. Got {report.rows}"
        )

    def test_plan_mode_is_not_capped(self, st, sim, ledger, monkeypatch):
        """Planning moves nothing, so a ceiling must not hide what a real pass would do."""
        monkeypatch.setenv("AIMARKET_ESCROW_MAX_USD_PER_PASS", "0.01")
        self._rows(st, ledger, 3)
        report = _mirror(st, signer_mod.PlanOnlySigner()).run(now=_NOW)
        assert report.outcomes.get(mirror.OUTCOME_PLANNED) == 3, report.outcomes

    def test_the_defaults_are_bounded(self, monkeypatch):
        """An operator who sets nothing must still get a bound, not unlimited spend."""
        for var in ("AIMARKET_ESCROW_MAX_USD_PER_PASS", "AIMARKET_ESCROW_MAX_USD_PER_DAY"):
            monkeypatch.delenv(var, raising=False)
        assert config.max_usd_per_pass() > 0
        assert config.max_usd_per_day() >= config.max_usd_per_pass()
        described = config.describe()
        assert described["max_usd_per_pass"] and described["max_usd_per_day"]

    def test_a_nonsense_ceiling_falls_back_to_the_default(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_ESCROW_MAX_USD_PER_PASS", "banana")
        assert config.max_usd_per_pass() == 5.0
        monkeypatch.setenv("AIMARKET_ESCROW_MAX_USD_PER_PASS", "-10")
        assert config.max_usd_per_pass() == 0.0, "negative clamps to 0 (= no cap), not below"


class TestAWindowIsCollectedWhole:
    """A nonce window's one authorization carries every call in it (since 2026-09-22), but
    the ledger records each call under its own receipt. Guard 2 compared the window's total
    with the newest receipt alone, so any window of two or more calls was refused as
    over-collection and never collected (found by the 2026-10-08 review)."""

    R1, R2, R3 = "0x" + "31" * 32, "0x" + "32" * 32, "0x" + "33" * 32

    def _window(self, st, ledger, served=(True, True, True)):
        amounts = (1_000_000, 2_000_000, 3_000_000)
        for i, (rid, units) in enumerate(zip((self.R1, self.R2, self.R3), amounts)):
            if served[i]:
                ledger(receipt_id=rid, cents=100)
            if i:
                st.abandon((self.R1, self.R2)[i - 1], store.SUPERSEDED_REASON)
            _row(st, receipt_id=rid, amount_units=units, nonce=0)

    def test_the_window_total_is_backed_by_every_call_in_it(self, st, ledger, sim):
        self._window(st, ledger)
        report = _mirror(st, signer_mod.PlanOnlySigner()).run(now=_NOW)
        assert report.outcomes == {mirror.OUTCOME_PLANNED: 1}, report.rows
        assert st.get(self.R3).status == store.PLANNED

    def test_a_call_in_the_window_the_ledger_never_charged_still_blocks(self, st, ledger, sim):
        self._window(st, ledger, served=(True, False, True))
        report = _mirror(st, signer_mod.PlanOnlySigner()).run(now=_NOW)
        assert report.outcomes.get(mirror.OUTCOME_BLOCKED) == 1
        assert "over-collect" in report.rows[0]["detail"]
