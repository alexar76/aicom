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
    monkeypatch.delenv("AIFACTORY_UNSAFE_ALLOW_HOST_GENERATED_CODE", raising=False)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("Unsafe process fallback"))
    out = isolation.start_sandbox(sb.id, command=["python3", "-c", "print(1)"])
    assert out.status == SandboxStatus.FAILED
    assert "generated_code_isolation_required" in out.error


def test_default_execution_mode_container_when_required(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AIFACTORY_SANDBOX_REQUIRE_CONTAINER", "1")
    sb = SandboxIsolation(sandbox_base_dir=str(tmp_path / "sandboxes"))
    assert sb.execution_mode == "container"


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


def test_process_mode_default_refuses_actual_secret_read(isolation, tmp_path, monkeypatch):
    import sys

    monkeypatch.delenv("AIFACTORY_UNSAFE_ALLOW_HOST_GENERATED_CODE", raising=False)
    monkeypatch.delenv("AIFACTORY_PROD", raising=False)
    monkeypatch.delenv("AIFACTORY_PRODUCTION", raising=False)
    secret = tmp_path / "factory-secret"
    secret.write_text("canary-only")
    leaked = tmp_path / "leaked-secret"
    code_dir = tmp_path / "product-code"
    sandbox = isolation.create_sandbox("evil", str(code_dir))
    isolation.execution_mode = "process"
    isolation.require_container = False
    command = [sys.executable, "-c", f"from pathlib import Path; Path({str(leaked)!r}).write_text(Path({str(secret)!r}).read_text())"]
    out = isolation.start_sandbox(sandbox.id, command=command)
    assert out.status == SandboxStatus.FAILED
    assert not leaked.exists()


def test_private_process_opt_in_still_scrubs_factory_credentials(isolation, tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_UNSAFE_ALLOW_HOST_GENERATED_CODE", "1")
    for name in ("AIFACTORY_PROD", "AIFACTORY_PRODUCTION", "AIFACTORY_DEMO_READONLY", "AIFACTORY_SANDBOX_REQUIRE_CONTAINER"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("JWT_SECRET_KEY", "secret-canary")
    monkeypatch.setenv("DOCKER_HOST", "tcp://private-daemon:2376")
    captured = {}

    def fake_popen(command, **kwargs):
        captured.update(kwargs["env"])
        return MagicMock(pid=12345)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    sandbox = isolation.create_sandbox("local", str(tmp_path / "product-code"))
    isolation.execution_mode = "process"
    isolation.require_container = False
    out = isolation.start_sandbox(sandbox.id, command=["python3", "-c", "print(1)"])
    assert out.status == SandboxStatus.RUNNING
    assert "JWT_SECRET_KEY" not in captured and "DOCKER_HOST" not in captured
