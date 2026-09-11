"""Sandbox preview environment preparation."""

from __future__ import annotations

from pathlib import Path

from web.backend.services.sandbox_preview_env import (
    build_fastapi_preview_env,
    code_requires_postgres,
)


def test_code_requires_postgres_detects_compose_stack(tmp_path: Path) -> None:
    root = tmp_path / "prod"
    root.mkdir()
    (root / "docker-compose.yml").write_text(
        "services:\n  postgres:\n    image: postgres:16\n  api:\n    build: .\n",
        encoding="utf-8",
    )
    (root / "backend").mkdir()
    (root / "backend" / "app").mkdir()
    (root / "backend" / "app" / "models.py").write_text(
        "from sqlalchemy.dialects.postgresql import UUID\n",
        encoding="utf-8",
    )
    assert code_requires_postgres(root) is True


def test_sqlite_env_for_simple_fastapi(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    root = tmp_path / "landing"
    root.mkdir()
    (root / "app").mkdir()
    (root / "app" / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
    env, meta = build_fastapi_preview_env(
        sandbox_id="test-sb",
        code_dir=root,
        cwd=root,
        base_env={},
    )
    assert "sqlite" in env["DATABASE_URL"].lower()
    assert meta.get("postgres_ephemeral") is not True
    assert (root / "data").is_dir()


def test_build_fastapi_preview_env_skips_pip_when_postgres_and_no_docker(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "pg_prod"
    backend = root / "backend"
    backend.mkdir(parents=True)
    (root / "docker-compose.yml").write_text(
        "services:\n  postgres:\n    image: postgres:16\n",
        encoding="utf-8",
    )
    (backend / "app").mkdir()
    (backend / "app" / "db.py").write_text("postgresql://user:pass@postgres/db\n", encoding="utf-8")

    pip_called = {"n": 0}

    def fake_pip(*_a, **_k):
        pip_called["n"] += 1

    monkeypatch.setattr(
        "web.backend.services.sandbox_preview_env._pip_install_requirements",
        fake_pip,
    )
    monkeypatch.setattr(
        "web.backend.services.sandbox_docker.docker_available",
        lambda: False,
    )

    env, meta = build_fastapi_preview_env(
        sandbox_id="sb-skip",
        code_dir=root,
        cwd=backend,
        base_env={},
        skip_heavy_setup=True,
    )

    assert meta.get("skip_heavy_setup") is True
    assert meta.get("postgres_status") == "docker_unavailable"
    assert pip_called["n"] == 0
    assert "preview_python" not in meta


def test_preview_venv_isolated_from_factory_python(tmp_path: Path, monkeypatch) -> None:
    """pip/uvicorn for sandbox previews must not use the factory sys.executable."""
    import sys
    from unittest.mock import MagicMock, patch

    root = tmp_path / "prod"
    backend = root / "backend"
    backend.mkdir(parents=True)
    (backend / "requirements.txt").write_text("httpx\n", encoding="utf-8")
    (backend / "app").mkdir()
    (backend / "app" / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")

    fake_factory = Path("/fake/factory/python")
    preview_py = root / ".aicom_sandbox" / "test_sb" / "preview-venv" / "bin" / "python"
    preview_py.parent.mkdir(parents=True)
    preview_py.write_text("", encoding="utf-8")

    def fake_preview_venv(_code_dir: Path, _sid: str) -> Path:
        return preview_py

    pip_calls: list[list[str]] = []

    def capture_run(cmd, **kwargs):
        pip_calls.append(list(cmd))
        if cmd[:3] == [str(preview_py), "-m", "pip"] and "-r" in cmd:
            return MagicMock(returncode=0, stdout="", stderr="")
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        "web.backend.services.sandbox_preview_env._preview_venv_python",
        fake_preview_venv,
    )
    with patch("web.backend.services.sandbox_preview_env.subprocess.run", side_effect=capture_run):
        env, meta = build_fastapi_preview_env(
            sandbox_id="test-sb",
            code_dir=root,
            cwd=backend,
            base_env={},
        )

    assert meta["preview_python"] == str(preview_py)
    assert all(str(preview_py) in call for call in pip_calls)
    assert not any(str(fake_factory) in call for call in pip_calls)
    assert sys.executable not in {call[0] for call in pip_calls}


def test_docker_cli_env_rewrites_dind_hostname(monkeypatch) -> None:
    from web.backend.services.sandbox_docker import docker_cli_env, docker_daemon_host

    monkeypatch.setenv("DOCKER_HOST", "tcp://docker-dind:2376")
    env = docker_cli_env({})
    assert env["DOCKER_HOST"] == "tcp://docker:2376"
    monkeypatch.setenv("DOCKER_HOST", "tcp://docker-dind:2376")
    assert docker_daemon_host() == "docker"


def test_docker_daemon_host_unix_socket(monkeypatch) -> None:
    from web.backend.services.sandbox_docker import docker_daemon_host

    monkeypatch.setenv("DOCKER_HOST", "unix:///var/run/docker.sock")
    assert docker_daemon_host() == "127.0.0.1"
