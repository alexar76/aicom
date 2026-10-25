"""The test gate must preserve failures and never turn coverage into a passing verdict."""

from __future__ import annotations

import contextlib
import subprocess
import sys
from unittest.mock import Mock

import pytest

from scripts import run_factory_pytest_ci as runner


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AIFACTORY_PYTEST_HARD_CAP_SEC", "10")
    export = Mock(return_value=subprocess.CompletedProcess([], 0))
    monkeypatch.setattr(runner.subprocess, "run", export)
    return tmp_path, export


@pytest.mark.parametrize("code", [0, 1, 2, 3, 4, 5])
def test_preserves_real_child_exit_status(harness, monkeypatch, code):
    root, export = harness
    (root / "coverage.json").write_text("stale success")
    monkeypatch.setattr(runner, "_pytest_argv", lambda: [sys.executable, "-c", f"raise SystemExit({code})"])

    assert runner.main() == code
    assert export.call_count == (2 if code == 0 else 0)
    assert not (root / "coverage.json").exists()


@pytest.mark.parametrize("coverage_exists", [False, True])
def test_deadline_fails_even_if_coverage_exists_and_sigterm_exits_zero(harness, monkeypatch, coverage_exists):
    root, export = harness
    monkeypatch.setenv("AIFACTORY_PYTEST_HARD_CAP_SEC", "1")
    script = (
        "import signal,time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM, lambda *_: exit(0)); "
        + ("Path('.coverage').touch(); " if coverage_exists else "")
        + "print('ready', flush=True); time.sleep(60)"
    )
    original_popen = subprocess.Popen

    def spawn(*args, **kwargs):
        # Synchronize on the child's readiness; process startup can exceed a second
        # on a loaded workstation and is unrelated to the timeout verdict being tested.
        proc = original_popen(*args, stdout=subprocess.PIPE, **kwargs)
        assert proc.stdout.readline() == b"ready\n"
        proc.stdout.close()
        return proc

    monkeypatch.setattr(runner.subprocess, "Popen", spawn)
    monkeypatch.setattr(runner, "_pytest_argv", lambda: [sys.executable, "-c", script])
    assert runner.main() == 124
    assert (root / ".coverage").exists() is coverage_exists
    export.assert_not_called()


@pytest.mark.parametrize("value", ["0", "-1", "nan", "abc"])
def test_invalid_deadline_is_reported(harness, monkeypatch, capsys, value):
    monkeypatch.setenv("AIFACTORY_PYTEST_HARD_CAP_SEC", value)
    assert runner.main() == 2
    assert "positive integer" in capsys.readouterr().err


def test_coverage_export_failure_is_not_success(harness, monkeypatch):
    _, export = harness
    export.return_value.returncode = 1
    monkeypatch.setattr(runner, "_pytest_argv", lambda: [sys.executable, "-c", "pass"])
    assert runner.main() == 1


def test_payment_coverage_failure_is_not_success(harness, monkeypatch):
    _, export = harness
    export.side_effect = [subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], 1)]
    monkeypatch.setattr(runner, "_pytest_argv", lambda: [sys.executable, "-c", "pass"])
    assert runner.main() == 1
    assert "check_payment_coverage.py" in export.call_args.args[0][1]


def test_missing_executable_reports_failure(harness, monkeypatch, capsys):
    root, export = harness
    monkeypatch.setattr(runner, "_pytest_argv", lambda: [str(root / "missing-python")])
    assert runner.main() == 2
    assert "Could not start" in capsys.readouterr().err
    export.assert_not_called()


def test_deadline_stops_descendants_even_when_parent_has_already_exited(harness, monkeypatch):
    import os
    import signal
    import time

    root, _ = harness
    ready = root / "child-ready"
    child_script = (
        "import signal,time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"Path({str(ready)!r}).touch(); time.sleep(60)"
    )
    parent_script = (
        "import subprocess,sys; "
        f"subprocess.Popen([sys.executable, '-c', {child_script!r}])"
    )
    proc = subprocess.Popen([sys.executable, "-c", parent_script], start_new_session=True)
    terminated = False
    try:
        proc.wait(timeout=10)
        deadline = time.monotonic() + 10
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists(), "child never started"
        sent = []
        original_killpg = os.killpg

        def send(group, sig):
            sent.append((group, sig))
            return original_killpg(group, sig)

        monkeypatch.setattr(os, "killpg", send)
        # An exited group leader must not stop us from signalling its descendants.
        runner._terminate(proc, grace_sec=0.1)
        terminated = True
        assert sent == [(proc.pid, signal.SIGTERM), (proc.pid, signal.SIGKILL)]
    finally:
        # Do not signal an already destroyed group again: on macOS a sandbox
        # can report EPERM for that stale PGID; it could also have been reused.
        if not terminated:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()


def test_runner_uses_the_current_python(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["runner", "tests/test_cost_guard.py"])
    args = runner._pytest_argv()
    assert args[:3] == [sys.executable, "-m", "coverage"]
    assert args[-1] == "tests/test_cost_guard.py"

