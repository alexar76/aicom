"""Host disk monitor thresholds and Telegram gating."""

from __future__ import annotations

from pathlib import Path

import pytest

from web.backend.services import host_disk_monitor as mon


def test_classify_warning_when_low_free_gb(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(mon, "warn_free_gb", lambda: 5.0)
    monkeypatch.setattr(mon, "crit_free_gb", lambda: 0.5)
    monkeypatch.setattr(mon, "warn_used_pct", lambda: 85.0)
    monkeypatch.setattr(mon, "crit_used_pct", lambda: 92.0)

    class U:
        total = 100 * 1024**3
        free = 14 * 1024**3  # 14 GB free on 100 GB → 86% used → warning

    monkeypatch.setattr(mon.shutil, "disk_usage", lambda _p: U)
    snap = mon.classify_disk_usage(tmp_path)
    assert snap is not None
    assert snap.level == "warning"


def test_telegram_skipped_when_disabled(monkeypatch):
    monkeypatch.setattr(mon, "worst_disk_snapshot", lambda: ("warning", []))
    monkeypatch.setattr(mon, "telegram_disk_notify_enabled", lambda: False)
    assert mon.check_disk_and_notify_telegram() == "warning"


def test_normalize_disk_monitor_settings_clamps_and_orders():
    out = mon.normalize_disk_monitor_settings(
        {
            "disk_warn_used_pct": 50,
            "disk_crit_used_pct": 40,
            "disk_warn_free_gb": 0.01,
            "disk_crit_free_gb": 10,
            "disk_alert_cooldown_hours": 0.1,
            "disk_monitor_interval_minutes": 0,
            "telegram_notify_host_disk": 0,
        }
    )
    assert out["disk_warn_used_pct"] <= out["disk_crit_used_pct"]
    assert out["disk_warn_free_gb"] >= out["disk_crit_free_gb"]
    assert out["disk_warn_free_gb"] == 0.1  # clamped from 0.01
    assert out["disk_crit_free_gb"] == 0.1  # cannot exceed warn_gb
    assert out["disk_monitor_interval_minutes"] >= 1
    assert out["telegram_notify_host_disk"] is False


def test_disk_monitor_settings_from_config():
    class Cfg:
        def get(self, key, default=None):
            if key == "general":
                return {"disk_warn_used_pct": 88, "disk_crit_used_pct": 95}
            return default

    s = mon.disk_monitor_settings_from_config(Cfg())
    assert s["disk_warn_used_pct"] == 88.0
    assert s["disk_crit_used_pct"] == 95.0
