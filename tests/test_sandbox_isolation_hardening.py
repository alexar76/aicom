"""SandboxIsolation container mode — hardened docker run invocation."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from security.docker_sandbox import assert_hardened_flags_present
from security.sandbox_isolation import SandboxIsolation, SandboxStatus


@pytest.fixture
def isolation(tmp_path: Path) -> SandboxIsolation:
    code = tmp_path / "product-code"
    code.mkdir()
    (code / "index.html").write_text("<html></html>", encoding="utf-8")
    return SandboxIsolation(
        sandbox_base_dir=str(tmp_path / "sandboxes"),
        execution_mode="container",
        enable_network=False,
    )


def test_container_mode_uses_hardened_docker_flags(isolation: SandboxIsolation, tmp_path: Path, monkeypatch):
    code_dir = tmp_path / "product-code"
    sb = isolation.create_sandbox("prod-1", str(code_dir))
    captured: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured.append(list(cmd))
        return MagicMock(returncode=0, stdout="container-id\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = isolation.start_sandbox(sb.id, command=["python3", "-m", "http.server", "9001"])

    assert out.status == SandboxStatus.RUNNING
    assert len(captured) == 1
    assert_hardened_flags_present(captured[0])
    assert "--network" in captured[0] and "none" in captured[0]
    assert any("sandbox-" in str(x) for x in captured[0])


def test_process_fallback_when_container_fails_and_not_required(isolation: SandboxIsolation, tmp_path: Path, monkeypatch):
    code_dir = tmp_path / "product-code"
    sb = isolation.create_sandbox("prod-2", str(code_dir))

    def fail_docker(*args, **kwargs):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(subprocess, "run", fail_docker)
    isolation.execution_mode = "container"
    isolation.require_container = False
    out = isolation.start_sandbox(sb.id, command=["python3", "-c", "print(1)"])
    assert out.status in (SandboxStatus.RUNNING, SandboxStatus.FAILED)


def test_require_container_blocks_process_fallback(isolation: SandboxIsolation, tmp_path: Path, monkeypatch):
    code_dir = tmp_path / "product-code"
    sb = isolation.create_sandbox("prod-3", str(code_dir))

    def fail_docker(*args, **kwargs):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(subprocess, "run", fail_docker)
    isolation.execution_mode = "container"
    isolation.require_container = True
    out = isolation.start_sandbox(sb.id, command=["python3", "-c", "print(1)"])
    assert out.status == SandboxStatus.FAILED
    assert "required" in (out.error or "").lower()
