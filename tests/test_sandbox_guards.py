"""Sandbox host resource planning."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from web.backend.services import sandbox_guards as guards
from tests.split_source import read_split


def test_enforce_blocks_when_at_concurrency_cap(monkeypatch):
    monkeypatch.setenv("AIFACTORY_SANDBOX_MAX_CONCURRENT", "1")
    active = {"sb1": {"status": "running", "expires_at": 9999999999.0}}
    with pytest.raises(HTTPException) as exc:
        guards.enforce_concurrency_limit(active, storefront=False)
    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "sandbox_busy"


def test_admin_start_evicts_when_at_the_cap():
    """Files tab used to 503 while storefront evicted; both must free a slot."""
    src = read_split(Path(__file__).resolve().parents[1] / "web" / "backend" / "api" / "sandbox.py")
    fn = src[src.index("def _ensure_sandbox_capacity") : src.index("def _start_sandbox_for_product")]
    # The registry lives on web.backend.api.sandbox; the helper reads it there at call time.
    assert "while count_running_sandboxes(sandbox_api._active_sandboxes) >= cap:" in fn
    assert "if storefront:" not in fn
    active = {
        "old": {"status": "running", "expires_at": 1.0},
        "live": {"status": "running", "expires_at": 9999999999.0},
    }
    n = guards.prune_expired_sandboxes(active)
    assert n == 1
    assert "old" not in active
    assert "live" in active


def test_full_tier_when_disk_and_memory_ok(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(guards, "host_disk_free_gb", lambda _p: 10.0)
    monkeypatch.setattr(guards, "host_mem_available_mb", lambda: 4096)
    plan = guards.evaluate_sandbox_resource_plan(tmp_path, has_static_preview=True)
    assert plan.tier == "full"


def test_degraded_when_low_disk(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(guards, "host_disk_free_gb", lambda _p: 0.5)
    monkeypatch.setattr(guards, "host_mem_available_mb", lambda: 4096)
    plan = guards.evaluate_sandbox_resource_plan(tmp_path, has_static_preview=True)
    assert plan.tier == "degraded"
    assert "low_disk" in plan.reasons
