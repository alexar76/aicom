"""Calibrated slashing: cool-down, daily cap, durable counters, verify-first escalation.

Slash is a trust floor, not a death penalty: failures below the threshold cost trust
only; a slash fires at most once per cool-down; the rolling daily cap keeps one bad
day from zeroing a new agent; and a Metis verified-failure escalates to stake only
on repeat offenses (the escrow refund already protected the buyer).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.signing import Signer
from aimarket_hub.slash_sync import SlashRegistry
from aimarket_hub.supply_security import SupplySecurity, SupplySecurityPolicy


class TestWindowConfigValidation:
    """A non-positive/garbage slash WINDOW must fall back to the documented default —
    it would otherwise build an invalid SQLite modifier and silently fail-OPEN the ladder."""

    def test_negative_window_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_SUPPLY_SLASH_FAILURE_WINDOW_S", "-1")
        monkeypatch.setenv("AIMARKET_SUPPLY_VERIFIED_FAIL_WINDOW_S", "-1")
        pol = SupplySecurityPolicy.from_config(HubConfig())
        assert pol.slash_failure_window_s == 600.0
        assert pol.verified_fail_window_s == 86400.0

    def test_empty_and_garbage_window_falls_back(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_SUPPLY_SLASH_FAILURE_WINDOW_S", "")
        pol = SupplySecurityPolicy.from_config(HubConfig())
        assert pol.slash_failure_window_s == 600.0
        monkeypatch.setenv("AIMARKET_SUPPLY_SLASH_FAILURE_WINDOW_S", "notanumber")
        assert SupplySecurityPolicy.from_config(HubConfig()).slash_failure_window_s == 600.0

    def test_valid_window_is_honored(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_SUPPLY_SLASH_FAILURE_WINDOW_S", "42")
        assert SupplySecurityPolicy.from_config(HubConfig()).slash_failure_window_s == 42.0


def _make_sec(db, tmp_path, registry=None, **policy):
    sec = SupplySecurity(
        db, HubConfig(), signer=Signer(key_path=tmp_path / "hub_key"), slash_registry=registry,
    )
    sec.policy.relaxed = False
    sec.policy.min_stake_usd = 0.0
    sec.lumen = MagicMock()
    sec.lumen.score_entity.return_value = {"score": 0.5}
    for key, value in policy.items():
        setattr(sec.policy, key, value)
    return sec


@pytest.fixture
def db(tmp_path):
    return HubDatabase(db_path=str(tmp_path / "hub.db"))


def _fail(sec, publisher="pub-a", n=1):
    for _ in range(n):
        sec.record_invoke(
            publisher_id=publisher, consumer_id="c1", success=False,
            product_id="prod-x", capability_id="cap-x",
        )


class TestFailureStreakDurability:
    def test_streak_survives_restart(self, db, tmp_path):
        """The consecutive-failure counter is DB-backed: a restart is not an amnesty."""
        sec1 = _make_sec(db, tmp_path, slash_failure_threshold=3)
        db.supply_stake_add("pub-a", 100.0)
        _fail(sec1, n=2)
        assert db.supply_stake_get("pub-a") == 100.0  # below threshold: trust only

        sec2 = _make_sec(db, tmp_path, slash_failure_threshold=3)  # "restarted" hub
        _fail(sec2, n=1)
        assert db.supply_stake_get("pub-a") == 95.0  # 3rd failure fires 5%

    def test_success_clears_streak(self, db, tmp_path):
        sec = _make_sec(db, tmp_path, slash_failure_threshold=3)
        db.supply_stake_add("pub-a", 100.0)
        _fail(sec, n=2)
        sec.record_invoke(
            publisher_id="pub-a", consumer_id="c1", success=True,
            product_id="prod-x", capability_id="cap-x",
        )
        _fail(sec, n=2)
        assert db.supply_stake_get("pub-a") == 100.0  # streak was reset by the success


class TestCooldownAndDailyCap:
    def test_cooldown_suppresses_second_slash(self, db, tmp_path):
        sec = _make_sec(db, tmp_path, slash_failure_threshold=3, slash_cooldown_s=3600)
        db.supply_stake_add("pub-a", 100.0)
        _fail(sec, n=3)
        assert db.supply_stake_get("pub-a") == 95.0
        # A second full streak inside the cool-down costs trust, not stake.
        _fail(sec, n=3)
        assert db.supply_stake_get("pub-a") == 95.0
        events = db.supply_slash_events_recent("pub-a")
        assert len(events) == 1

    def test_cooldown_zero_disables(self, db, tmp_path):
        sec = _make_sec(db, tmp_path, slash_failure_threshold=3, slash_cooldown_s=0,
                        slash_daily_cap_usd=0)
        db.supply_stake_add("pub-a", 100.0)
        _fail(sec, n=3)
        _fail(sec, n=3)
        assert db.supply_stake_get("pub-a") == pytest.approx(90.25)  # 5% twice, compounding

    def test_daily_cap_bounds_total(self, db, tmp_path):
        sec = _make_sec(db, tmp_path, slash_failure_threshold=1, slash_cooldown_s=0,
                        slash_daily_cap_usd=7.0)
        db.supply_stake_add("pub-a", 100.0)
        _fail(sec, n=1)  # -5.00 (5% of 100, under $5 cap → 5.0)
        _fail(sec, n=1)  # cap leaves only 2.00 of headroom
        _fail(sec, n=1)  # cap reached → no slash
        events = db.supply_slash_events_recent("pub-a")
        total = sum(e["amount_usd"] for e in events)
        assert total == pytest.approx(7.0)
        assert db.supply_stake_get("pub-a") == pytest.approx(93.0)

    def test_slash_event_log_is_audit_trail(self, db, tmp_path):
        sec = _make_sec(db, tmp_path, slash_failure_threshold=1, slash_cooldown_s=0)
        db.supply_stake_add("pub-a", 100.0)
        _fail(sec, n=1)
        events = db.supply_slash_events_recent("pub-a")
        assert len(events) == 1
        assert events[0]["reason"] == "invoke_failure:prod-x/cap-x"

    def test_cooldown_expires_and_next_slash_fires(self, db, tmp_path):
        """The suppression must be time-bounded: after the cool-down elapses a new streak
        slashes again. Backdate the slash event to simulate the window passing. Pins the
        julianday age math against a UTC/localtime skew that would clamp age to 0 forever."""
        sec = _make_sec(db, tmp_path, slash_failure_threshold=3, slash_cooldown_s=3600)
        db.supply_stake_add("pub-a", 100.0)
        _fail(sec, n=3)
        assert db.supply_stake_get("pub-a") == 95.0
        # Age the slash event past the cool-down.
        db._conn.execute(
            "UPDATE supply_slash_events SET created_at = datetime('now','-7200 seconds') WHERE publisher_id='pub-a'"
        )
        db._conn.commit()
        assert db.supply_slash_last_age_s("pub-a") == pytest.approx(7200, abs=30)
        _fail(sec, n=3)
        assert db.supply_stake_get("pub-a") == pytest.approx(90.25)  # second slash fired
        assert len(db.supply_slash_events_recent("pub-a")) == 2

    def test_daily_cap_resets_after_window(self, db, tmp_path):
        """The cap is ROLLING 24h, not lifetime: once old slashes age out, headroom returns."""
        sec = _make_sec(db, tmp_path, slash_failure_threshold=1, slash_cooldown_s=0,
                        slash_daily_cap_usd=7.0)
        db.supply_stake_add("pub-a", 100.0)
        _fail(sec, n=1); _fail(sec, n=1); _fail(sec, n=1)  # hits the $7 cap
        assert db.supply_slash_total_recent("pub-a", hours=24.0) == pytest.approx(7.0)
        db._conn.execute("UPDATE supply_slash_events SET created_at = datetime('now','-25 hours')")
        db._conn.commit()
        assert db.supply_slash_total_recent("pub-a", hours=24.0) == 0.0  # aged out of the window
        assert db.supply_slash_total_recent("pub-a", hours=26.0) == pytest.approx(7.0)  # scale pinned
        _fail(sec, n=1)
        assert db.supply_slash_total_recent("pub-a", hours=24.0) > 0.0  # headroom restored → slashed again

    def test_fault_window_expiry_excludes_stale_faults(self, db, tmp_path):
        """Faults older than the window must not count toward the streak (no over-slash),
        and a fresh one must (predicate not vacuously false)."""
        sec = _make_sec(db, tmp_path, slash_failure_threshold=3, slash_failure_window_s=600)
        db.supply_stake_add("pub-a", 100.0)
        _fail(sec, n=2)
        db._conn.execute(
            "UPDATE supply_fault_events SET created_at = datetime('now','-2 hours') WHERE publisher_id='pub-a'"
        )
        db._conn.commit()
        assert db.supply_fault_count_recent("pub-a", "invoke_failure", 600) == 0  # stale excluded
        _fail(sec, n=1)  # one fresh failure — streak is effectively 1, below threshold
        assert db.supply_fault_count_recent("pub-a", "invoke_failure", 600) == 1  # fresh counted
        assert db.supply_stake_get("pub-a") == 100.0  # no slash on stale + 1 fresh


class TestVerifiedFailureEscalation:
    def _rejection(self):
        return {"type": "verification_rejection", "reason": "verify_failed",
                "verify_score": 0.12, "signature": {"value": "sig"}}

    def _vfail(self, sec, publisher="pub-a", consumer="c1", paid=True):
        sec.record_verified_failure(
            publisher_id=publisher, product_id="prod-x", capability_id="cap-x",
            consumer_id=consumer, paid=paid, rejection=self._rejection(),
        )

    def test_single_verified_fail_costs_trust_not_stake(self, db, tmp_path):
        sec = _make_sec(db, tmp_path, verified_fail_threshold=3)
        db.supply_stake_add("pub-a", 100.0)
        self._vfail(sec)
        assert db.supply_stake_get("pub-a") == 100.0
        edges = [e for e in db.trust_list_edges(limit=100) if e[3] == "verified_failure"]
        assert edges, "a paid verified failure must at least ding trust"
        # The ding is attributed to the CONSUMER, not the hub anchor (griefing defense).
        assert edges[0][0] == "c1"

    def test_advisory_verified_fail_is_a_noop(self, db, tmp_path):
        """Unpaid (advisory/sandbox/crypto-off) verdicts never touch the stake ladder —
        the buyer risked nothing and controls the intent, so it is not economic evidence."""
        sec = _make_sec(db, tmp_path, verified_fail_threshold=1, verified_fail_min_consumers=1,
                        slash_cooldown_s=0)
        db.supply_stake_add("pub-a", 100.0)
        for i in range(10):
            self._vfail(sec, consumer=f"grief-{i}", paid=False)
        assert db.supply_stake_get("pub-a") == 100.0
        assert db.supply_fault_count_recent("pub-a", "verified_failure", 86400) == 0
        assert [e for e in db.trust_list_edges(limit=100) if e[3] == "verified_failure"] == []

    def test_single_consumer_cannot_slash_alone(self, db, tmp_path):
        """One buyer's repeated paid failures are ONE voice: below the distinct-consumer
        floor, no slash — mirrors the weak-tier 'a lone issuer moves nothing' rule."""
        sec = _make_sec(db, tmp_path, verified_fail_threshold=3, verified_fail_min_consumers=2,
                        slash_cooldown_s=0)
        db.supply_stake_add("pub-a", 100.0)
        for _ in range(6):
            self._vfail(sec, consumer="lone-griefer")
        assert db.supply_stake_get("pub-a") == 100.0  # count met, distinct-consumers not
        assert db.supply_slash_events_recent("pub-a") == []

    def test_repeat_verified_fails_escalate_with_evidence(self, db, tmp_path):
        registry = SlashRegistry("https://hub-a.example")
        sec = _make_sec(db, tmp_path, registry=registry, verified_fail_threshold=3,
                        verified_fail_min_consumers=2, slash_cooldown_s=0)
        db.supply_stake_add("pub-a", 100.0)
        # 3 failures from 3 DISTINCT paying consumers → both gates met.
        for c in ("buyer-1", "buyer-2", "buyer-3"):
            self._vfail(sec, consumer=c)
        assert db.supply_stake_get("pub-a") == 95.0
        events = db.supply_slash_events_recent("pub-a")
        assert events[0]["evidence_kind"] == "verification_rejection"
        # The attestation federates carrying the rejection receipt as evidence.
        exported = registry.export()
        assert len(exported) == 1
        assert exported[0]["evidence_kind"] == "verification_rejection"
        assert exported[0]["evidence"]["reason"] == "verify_failed"

    def test_verified_fail_window_is_separate_from_invoke_failures(self, db, tmp_path):
        sec = _make_sec(db, tmp_path, slash_failure_threshold=3, verified_fail_threshold=3)
        db.supply_stake_add("pub-a", 100.0)
        _fail(sec, n=2)
        self._vfail(sec)
        # 2 invoke failures + 1 verified failure: neither ladder reached its threshold.
        assert db.supply_stake_get("pub-a") == 100.0

    def test_relaxed_mode_never_slashes(self, db, tmp_path):
        sec = _make_sec(db, tmp_path, verified_fail_threshold=1, verified_fail_min_consumers=1)
        sec.policy.relaxed = True
        db.supply_stake_add("pub-a", 100.0)
        self._vfail(sec)
        assert db.supply_stake_get("pub-a") == 100.0
