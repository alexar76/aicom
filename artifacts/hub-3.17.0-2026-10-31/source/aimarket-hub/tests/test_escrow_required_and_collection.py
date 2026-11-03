"""KI-11's two open items: closing the custodial door, and collecting without a person.

Both are off by default and both are refused rather than half-applied when their
prerequisites are missing — which is the property worth pinning, because the failure
mode they replace was silence: a hub that looked like it charged, and a claim nobody
ever presented.
"""

from __future__ import annotations

import asyncio

import pytest

from aimarket_hub import channels
from aimarket_hub.escrow_bridge import collector
from aimarket_hub.escrow_bridge import config as bridge_config


class TestTheCustodialDoorCanBeClosed:
    def test_it_is_open_by_default(self, monkeypatch):
        monkeypatch.delenv("AIMARKET_ESCROW_REQUIRED", raising=False)
        assert bridge_config.required() is False
        assert channels._escrow_required() is False

    def test_requiring_escrow_closes_it(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_ESCROW_REQUIRED", "1")
        assert channels._escrow_required() is True

    def test_requiring_escrow_without_the_bridge_refuses_BOTH_doors(self, monkeypatch):
        """The misconfiguration must not silently fall back to custody.

        `required and enabled` would have meant: operator asks for the strongest
        setting, forgets the master switch, and gets the weakest one with no signal.
        """
        monkeypatch.setenv("AIMARKET_ESCROW_REQUIRED", "1")
        monkeypatch.setenv("AIMARKET_ESCROW_BRIDGE_ENABLED", "0")
        assert channels._escrow_required() is True  # custodial path: closed
        assert bridge_config.enabled() is False     # escrow path: also closed

    def test_readiness_says_so_out_loud(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_ESCROW_REQUIRED", "1")
        monkeypatch.setenv("AIMARKET_ESCROW_BRIDGE_ENABLED", "0")
        report = channels.payment_readiness()
        assert report["escrow_required"] is True
        assert report["custodial_deposit_reachable"] is False
        assert "escrow_required_but_bridge_disabled" in report["blockers"]
        assert report["can_credit_channels"] is False

    def test_a_transfer_funded_open_is_refused_when_escrow_is_required(
        self, monkeypatch, tmp_path,
    ):
        monkeypatch.setenv("AIMARKET_ESCROW_REQUIRED", "1")
        ledger = channels.ChannelLedger(db_path=str(tmp_path / "closed.db"))
        result = ledger.open(
            deposit_usd=1.0,
            wallet="0x6E94c380d908531f9822035d6cc4c8D2B0186C9c",
            tx_hash="0x" + "ab" * 32,
        )
        assert "error" in result
        assert "AIMARKET_ESCROW_REQUIRED" in result["error"]
        # And it says what to send instead: the caller has already moved money.
        assert "escrow_channel_id" in result["error"]

    def test_the_same_open_works_when_escrow_is_not_required(self, monkeypatch, tmp_path):
        monkeypatch.delenv("AIMARKET_ESCROW_REQUIRED", raising=False)
        ledger = channels.ChannelLedger(db_path=str(tmp_path / "open.db"))
        result = ledger.open(
            deposit_usd=1.0,
            wallet="0x6E94c380d908531f9822035d6cc4c8D2B0186C9c",
            tx_hash="0x" + "ab" * 32,
        )
        # Whatever this hub decides about the deposit, it is not THIS refusal.
        assert "AIMARKET_ESCROW_REQUIRED" not in str(result.get("error", ""))


class TestCollectionIsOffUntilAsked:
    def test_no_interval_means_no_loop(self, monkeypatch):
        monkeypatch.delenv("AIMARKET_ESCROW_COLLECT_INTERVAL_S", raising=False)
        assert collector.interval_s() == 0
        assert "off" in collector.blocked_reason()

    def test_an_interval_is_floored_so_it_cannot_be_hammered(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_ESCROW_COLLECT_INTERVAL_S", "5")
        assert collector.interval_s() == 60

    def test_a_disabled_bridge_blocks_the_pass(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_ESCROW_COLLECT_INTERVAL_S", "600")
        monkeypatch.setenv("AIMARKET_ESCROW_BRIDGE_ENABLED", "0")
        assert "disabled" in collector.blocked_reason()
        assert collector.collect_once()["skipped"]

    def test_a_plan_only_hub_never_broadcasts_from_here_either(self, monkeypatch):
        """The CLI's guard is the bridge's, not the CLI's — so this door has it too."""
        monkeypatch.setenv("AIMARKET_ESCROW_COLLECT_INTERVAL_S", "600")
        monkeypatch.setenv("AIMARKET_ESCROW_BRIDGE_ENABLED", "1")
        monkeypatch.setenv("AIMARKET_ESCROW_SUBMIT_STRATEGY", "plan")
        monkeypatch.delenv("AIMARKET_ESCROW_PRIVATE_KEY", raising=False)
        monkeypatch.delenv("AIMARKET_ESCROW_SIGNER_URL", raising=False)
        assert collector.blocked_reason() != ""
        assert collector.collect_once()["skipped"]

    def test_the_loop_returns_at_once_when_collection_is_off(self, monkeypatch):
        monkeypatch.delenv("AIMARKET_ESCROW_COLLECT_INTERVAL_S", raising=False)
        # No sleep is injected: if the loop entered a cycle this would hang.
        asyncio.run(asyncio.wait_for(collector.run_forever(), timeout=2))

    def test_a_failing_pass_does_not_kill_the_loop(self, monkeypatch):
        """Not collecting is a revenue problem; crashing the hub is an availability one."""
        monkeypatch.setenv("AIMARKET_ESCROW_COLLECT_INTERVAL_S", "600")
        calls = {"n": 0}

        def _boom() -> dict:
            calls["n"] += 1
            raise RuntimeError("rpc is down")

        monkeypatch.setattr(collector, "collect_once", _boom)

        async def _drive() -> None:
            async def _sleep(_seconds: float) -> None:
                if calls["n"] >= 3:
                    raise asyncio.CancelledError
            with pytest.raises(asyncio.CancelledError):
                await collector.run_forever(sleep=_sleep)

        asyncio.run(_drive())
        assert calls["n"] >= 3, "the loop stopped at the first failure"

    def test_out_of_band_collections_are_confirmed_before_new_ones_are_sent(self, monkeypatch):
        """Order is load-bearing: a stuck row blocks every later row on its channel."""
        monkeypatch.setenv("AIMARKET_ESCROW_COLLECT_INTERVAL_S", "600")
        monkeypatch.setattr(collector, "blocked_reason", lambda: "")
        order: list[str] = []

        class _Report:
            @staticmethod
            def as_dict() -> dict:
                return {"outcomes": {}}

        class _Engine:
            def __init__(self, **_kwargs) -> None:
                pass

            def confirm(self, **_kwargs) -> _Report:
                order.append("confirm")
                return _Report()

            def run(self, **_kwargs) -> _Report:
                order.append("run")
                return _Report()

        import aimarket_hub.escrow_bridge.mirror as mirror_mod
        import aimarket_hub.escrow_bridge.store as store_mod

        monkeypatch.setattr(mirror_mod, "Mirror", _Engine)
        monkeypatch.setattr(store_mod, "AuthorizationStore", lambda *a, **k: object())

        collector.collect_once()
        assert order == ["confirm", "run"]
