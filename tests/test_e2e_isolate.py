"""E2E probes must not take down the pipeline worker process."""

from __future__ import annotations

from web.backend.services.e2e_isolate import run_e2e_in_subprocess


def test_e2e_isolate_returns_child_dict():
    rep = run_e2e_in_subprocess(
        module="tests.e2e_isolate_helpers",
        func="ok",
        product_id="prod-test",
        data_root="/tmp/data",
        timeout_sec=15,
    )
    assert rep.get("passed") is True
    assert rep.get("product_id") == "prod-test"
    assert rep.get("data_root") == "/tmp/data"


def test_e2e_isolate_survives_child_sigkill():
    rep = run_e2e_in_subprocess(
        module="tests.e2e_isolate_helpers",
        func="boom",
        product_id="prod-crash",
        data_root=None,
        timeout_sec=15,
    )
    assert rep.get("passed") is False
    assert rep.get("error") == "e2e_subprocess_exited"
    assert int(rep.get("returncode") or 0) != 0


def test_e2e_isolate_timeout_kills_child():
    rep = run_e2e_in_subprocess(
        module="tests.e2e_isolate_helpers",
        func="sleepy",
        product_id="prod-slow",
        data_root=None,
        timeout_sec=2,
    )
    assert rep.get("passed") is False
    assert rep.get("error") == "e2e_subprocess_timeout"


def test_e2e_isolate_skips_browser_when_cgroup_low(monkeypatch):
    from web.backend.services import e2e_isolate

    monkeypatch.setattr(e2e_isolate, "cgroup_memory_bytes", lambda: (3 * 1024 * 1024 * 1024, 4 * 1024 * 1024 * 1024))
    monkeypatch.setenv("AIFACTORY_BROWSER_E2E_MIN_FREE_MB", "1536")
    rep = e2e_isolate.run_e2e_in_subprocess(
        module="web.backend.services.browser_preview_e2e",
        func="run_browser_preview_e2e",
        product_id="prod-mem",
        data_root=None,
        timeout_sec=5,
    )
    assert rep.get("skipped") is True
    assert rep.get("error") == "e2e_skipped_low_memory"
