"""scripts/warden_feedback_notify.py: an unreadable summary is not a missed run."""
from __future__ import annotations

import calendar
import importlib.util
import io
import json
import time
import urllib.error
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "warden_feedback_notify.py"
RAN = "2026-10-05T09:09:51Z"
RAN_TS = calendar.timegm(time.strptime(RAN, "%Y-%m-%dT%H:%M:%SZ"))


@pytest.fixture
def notify(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("warden_feedback_notify", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.STATE = str(tmp_path / "state.json")
    sent: list[str] = []
    monkeypatch.setattr(mod, "send", sent.append)
    monkeypatch.setattr(mod, "load_env", lambda: None)
    mod.sent = sent
    return mod


def run(mod, monkeypatch, *, now, summary=None):
    def urlopen(req, timeout):
        if summary is None:
            raise urllib.error.URLError("timed out")
        return io.BytesIO(json.dumps(summary).encode())
    monkeypatch.setattr(mod.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(mod.time, "time", lambda: now)
    mod.main()
    return json.load(open(mod.STATE))


def test_one_failed_fetch_after_a_recent_run_says_nothing(notify, monkeypatch):
    run(notify, monkeypatch, now=RAN_TS + 60, summary={"ranAt": RAN, "status": "ok"})
    notify.sent.clear()
    state = run(notify, monkeypatch, now=RAN_TS + 3 * 86400)
    assert notify.sent == []
    assert state["fetch_fail"] == 1


def test_summary_unreachable_for_three_hours_is_its_own_page_once_a_day(notify, monkeypatch):
    run(notify, monkeypatch, now=RAN_TS + 60, summary={"ranAt": RAN, "status": "ok"})
    notify.sent.clear()
    t = RAN_TS + 3 * 86400
    for h in range(4):
        run(notify, monkeypatch, now=t + h * 3600)
    assert len(notify.sent) == 1
    assert "не читается 3 ч подряд" in notify.sent[0]
    assert "не запускалась" not in notify.sent[0]
    assert RAN in notify.sent[0]
    state = run(notify, monkeypatch, now=t + 5 * 3600, summary={"ranAt": RAN, "status": "ok"})
    assert state["fetch_fail"] == 0


def test_a_really_stale_run_pages_even_when_the_summary_is_unreadable(notify, monkeypatch):
    run(notify, monkeypatch, now=RAN_TS + 60, summary={"ranAt": RAN, "status": "ok"})
    notify.sent.clear()
    run(notify, monkeypatch, now=RAN_TS + 9 * 86400)
    assert len(notify.sent) == 1
    assert "не запускалась больше 8 дней" in notify.sent[0]
    assert f"последний известный запуск {RAN}" in notify.sent[0]


def test_stale_summary_pages_once_a_day(notify, monkeypatch):
    summary = {"ranAt": RAN, "status": "ok"}
    run(notify, monkeypatch, now=RAN_TS + 60, summary=summary)
    notify.sent.clear()
    run(notify, monkeypatch, now=RAN_TS + 9 * 86400, summary=summary)
    run(notify, monkeypatch, now=RAN_TS + 9 * 86400 + 3600, summary=summary)
    assert len(notify.sent) == 1
    assert "не запускалась больше 8 дней" in notify.sent[0]
