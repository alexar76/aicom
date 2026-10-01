"""Tests for pipeline worker wake notification."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from core.pipeline_worker_notify import notify_pipeline_worker_wake


def test_notify_posts_wake_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFACTORY_PIPELINE_WORKER_WAKE", "1")
    monkeypatch.setenv("AIFACTORY_WORKER_HEALTH_PORT", "8091")
    opened: list = []

    class FakeResp:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=0):
        opened.append((req.full_url, req.method, timeout))
        return FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    notify_pipeline_worker_wake()
    assert len(opened) == 1
    assert opened[0][0].endswith("/wake")
    assert opened[0][1] == "POST"


def test_notify_disabled_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFACTORY_PIPELINE_WORKER_WAKE", "0")
    with patch("urllib.request.urlopen") as mock_open:
        notify_pipeline_worker_wake()
        mock_open.assert_not_called()


def test_write_pipeline_state_triggers_wake(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from core import pipeline_state_writer as psw

    calls: list[str] = []

    def fake_wake() -> None:
        calls.append("wake")

    monkeypatch.setattr(psw, "notify_pipeline_worker_wake", fake_wake)
    monkeypatch.setattr(psw, "pipeline_uses_sql_store", lambda: False)
    monkeypatch.setattr(psw, "pipeline_json_path", lambda: tmp_path / "pipeline.json")

    state = {"products": {}, "task_queue": [], "current_task_id": None}
    assert psw.write_pipeline_state(state) is True
    assert calls == ["wake"]
