"""deploy/erc-8004/warden_feedback_watchdog.py: decide when to restart a dead refresh."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy" / "erc-8004" / "warden_feedback_watchdog.py"
NOW = 1_700_000_000  # fixed epoch for decide()


@pytest.fixture
def watch(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("warden_feedback_watchdog", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.STATE = str(tmp_path / "watchdog-state.json")
    mod.LAST_RUN = str(tmp_path / "last-run.json")
    monkeypatch.setattr(mod, "unit_busy", lambda unit=None: False)
    return mod


def ran(iso: str, status: str = "ok") -> dict:
    return {"ranAt": iso, "status": status}


def iso_at(ts: float) -> str:
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def test_fresh_ok_does_not_start(watch):
    start, reason = watch.decide(ran(iso_at(NOW - 3600)), {}, NOW)
    assert start is False
    assert "ok and fresh" in reason


def test_stale_ok_starts(watch):
    start, reason = watch.decide(ran(iso_at(NOW - 8 * 86400)), {}, NOW)
    assert start is True
    assert "stale" in reason


def test_failed_inside_retry_window_waits(watch):
    start, reason = watch.decide(ran(iso_at(NOW - 3600), status="failed"), {}, NOW)
    assert start is False
    assert "retry window" in reason


def test_failed_after_retry_window_starts(watch):
    start, reason = watch.decide(ran(iso_at(NOW - 7 * 3600), status="failed"), {}, NOW)
    assert start is True
    assert "status='failed'" in reason


def test_missing_last_run_starts(watch):
    start, reason = watch.decide(None, {}, NOW)
    assert start is True
    assert "missing" in reason


def test_cooldown_blocks_even_when_stale(watch):
    state = {"lastStartAt": NOW - 3600}
    start, reason = watch.decide(ran(iso_at(NOW - 10 * 86400)), state, NOW)
    assert start is False
    assert "cooldown" in reason


def test_busy_unit_skips(watch):
    start, reason = watch.decide(None, {}, NOW, busy=True)
    assert start is False
    assert "already running" in reason


def test_main_dry_run_does_not_write_state(watch, tmp_path, monkeypatch):
    path = tmp_path / "last-run.json"
    path.write_text(json.dumps(ran(iso_at(NOW - 10 * 86400))))
    started = []
    monkeypatch.setattr(watch, "start_unit", lambda **kw: started.append(kw))
    monkeypatch.setattr(watch.time, "time", lambda: NOW)
    rc = watch.main(["--dry-run", "--last-run", str(path), "--state", str(tmp_path / "state.json")])
    assert rc == 0
    assert started and started[0].get("dry_run") is True
    assert not (tmp_path / "state.json").exists()
