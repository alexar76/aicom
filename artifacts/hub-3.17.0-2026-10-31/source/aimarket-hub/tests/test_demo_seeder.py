"""Demo capability seeder — honesty flags and zeroed vanity metrics."""

from __future__ import annotations

from aimarket_hub.database import HubDatabase
from aimarket_hub.demo_seeder import DEMO_CAPABILITIES, seed_capabilities


def test_seed_marks_demo_and_zeros_vanity_metrics(tmp_path):
    db = HubDatabase(str(tmp_path / "hub.db"))
    assert db.count_capabilities("local") == 0

    n = seed_capabilities(db)
    assert n == len(DEMO_CAPABILITIES)
    assert db.count_capabilities("local") == len(DEMO_CAPABILITIES)

    caps = db.list_capabilities("local", limit=100)
    assert len(caps) == len(DEMO_CAPABILITIES)
    for cap in caps:
        assert cap.is_demo is True
        assert cap.p50_latency_ms == 0
        assert cap.success_rate_30d == 0.0


def test_seed_is_idempotent_when_caps_exist(tmp_path):
    db = HubDatabase(str(tmp_path / "hub.db"))
    first = seed_capabilities(db)
    second = seed_capabilities(db)
    assert first == len(DEMO_CAPABILITIES)
    assert second == 0
