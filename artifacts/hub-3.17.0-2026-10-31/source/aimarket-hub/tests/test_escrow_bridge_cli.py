"""The operator CLI — mostly a test that the safe commands stay safe.

``submit`` is the only command that can move funds, and reaching it takes three
independent things: the configured strategy, the confirmation phrase in the environment,
and ``--yes`` on the command line. Each is tested as a separate lock, because the point of
three locks is that no single mistake opens the door.
"""

from __future__ import annotations

import json

import pytest

from aimarket_hub.escrow_bridge import cli, config, store
from aimarket_hub.escrow_bridge.eip712 import crypto_available

pytestmark = pytest.mark.skipif(
    not crypto_available(), reason="eth-utils/eth-account not installed (platon venv)"
)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Never touch a real store or a real chain from a CLI test."""
    monkeypatch.setenv("AIMARKET_ESCROW_BRIDGE_DB_PATH", str(tmp_path / "bridge.db"))
    for var in ("AIMARKET_ESCROW_BRIDGE_ENABLED", "AIMARKET_ESCROW_SUBMIT_STRATEGY",
                "AIMARKET_ESCROW_SUBMIT_CONFIRM", "AIMARKET_ESCROW_PRIVATE_KEY",
                "AIMARKET_ESCROW_SIGNER_URL"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def _run(capsys, *argv):
    code = cli.main(list(argv))
    return code, capsys.readouterr().out


class TestReadOnlyCommands:
    def test_status_works_on_a_hub_that_never_enabled_the_bridge(self, capsys):
        """That is exactly when an operator is trying to understand it."""
        code, out = _run(capsys, "status", "--json")
        assert code == 0
        assert json.loads(out)["config"]["enabled"] is False

    def test_status_does_not_create_a_store(self, capsys, isolated):
        _run(capsys, "status", "--json")
        assert not (isolated / "bridge.db").exists(), (
            "inspecting a disabled bridge must leave nothing behind"
        )

    def test_flags_work_before_and_after_the_subcommand(self, capsys):
        """`status --json` is how an operator will actually type it."""
        assert _run(capsys, "status", "--json")[0] == 0
        assert _run(capsys, "--json", "status")[0] == 0

    def test_show_reports_a_missing_receipt_without_crashing(self, capsys):
        code, out = _run(capsys, "show", "0x" + "11" * 32, "--json")
        assert code == 1, "a script asking about one receipt should notice it is missing"
        assert "absent" in out or "not found" in out

    def test_status_reports_the_queue_once_something_is_stored(self, capsys, isolated):
        st = store.AuthorizationStore(str(isolated / "bridge.db"))
        st.record(
            receipt_id="0x" + "22" * 32, ledger_channel="ch_1",
            escrow_channel="0x" + "11" * 32, chain_id=8453,
            escrow_address="0x" + "ee" * 20, hub="0x" + "cc" * 20, token="0x" + "dd" * 20,
            depositor="0x" + "aa" * 20, amount_units=1_000_000, nonce=0,
            deadline=4_000_000_000, signature="0x" + "ab" * 65,
        )
        st.close()
        code, out = _run(capsys, "status", "--json")
        payload = json.loads(out)
        assert code == 0
        assert payload["store"]["unsubmitted_usd"] == 1.0
        assert len(payload["queue"]) == 1
        # The buyer's signature is a credential, not operator-facing data.
        assert "ab" * 65 not in out


class TestActionCommandsNeedTheBridgeOn:
    @pytest.mark.parametrize("command", ["plan", "confirm"])
    def test_they_refuse_while_the_bridge_is_disabled(self, capsys, command):
        code, out = _run(capsys, command, "--json")
        assert code == 1 and "disabled" in out

    def test_submit_refuses_while_the_bridge_is_disabled(self, capsys):
        code, out = _run(capsys, "submit", "--yes", "--json")
        assert code == 1 and "disabled" in out


class TestSubmitHasThreeIndependentLocks:
    @pytest.fixture(autouse=True)
    def enabled(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_ESCROW_BRIDGE_ENABLED", "1")

    def test_lock_one_the_command_line_flag(self, capsys, monkeypatch):
        monkeypatch.setenv("AIMARKET_ESCROW_SUBMIT_STRATEGY", "env")
        monkeypatch.setenv("AIMARKET_ESCROW_PRIVATE_KEY", "0x" + "11" * 32)
        monkeypatch.setenv("AIMARKET_ESCROW_SUBMIT_CONFIRM", config.SUBMIT_CONFIRM_PHRASE)
        code, out = _run(capsys, "submit", "--json")     # no --yes
        assert code == 1 and "--yes" in out

    def test_lock_two_the_environment_confirmation(self, capsys, monkeypatch):
        monkeypatch.setenv("AIMARKET_ESCROW_SUBMIT_STRATEGY", "env")
        monkeypatch.setenv("AIMARKET_ESCROW_PRIVATE_KEY", "0x" + "11" * 32)
        code, out = _run(capsys, "submit", "--yes", "--json")
        assert code == 1 and "SUBMIT_CONFIRM" in out

    def test_lock_three_the_strategy_itself(self, capsys, monkeypatch):
        monkeypatch.setenv("AIMARKET_ESCROW_SUBMIT_CONFIRM", config.SUBMIT_CONFIRM_PHRASE)
        code, out = _run(capsys, "submit", "--yes", "--json")
        assert code == 1 and "plan" in out

    def test_plan_stays_plan_even_on_a_fully_armed_hub(self, capsys, monkeypatch, isolated):
        """The safe command must stay safe on a hub configured to broadcast."""
        monkeypatch.setenv("AIMARKET_ESCROW_SUBMIT_STRATEGY", "env")
        monkeypatch.setenv("AIMARKET_ESCROW_PRIVATE_KEY", "0x" + "11" * 32)
        monkeypatch.setenv("AIMARKET_ESCROW_SUBMIT_CONFIRM", config.SUBMIT_CONFIRM_PHRASE)
        code, out = _run(capsys, "plan", "--json")
        assert code == 0
        assert json.loads(out)["dry_run"] is True
