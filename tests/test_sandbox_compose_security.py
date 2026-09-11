"""Security boundary for model-authored Docker Compose previews."""

from __future__ import annotations

from pathlib import Path

import pytest

from web.backend.services.sandbox_compose_preview import (
    _compose_cli_env,
    start_compose_preview,
    validate_generated_compose,
)


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "docker-compose.yml"
    path.write_text(body, encoding="utf-8")
    return path


def test_reference_compose_is_accepted(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
services:
  api:
    build: .
    ports:
      - "${WEB_HOST_PORT:-9088}:8000"
    environment:
      PORT: "8000"
""",
    )
    assert validate_generated_compose(path, tmp_path) == []


@pytest.mark.parametrize(
    "fragment, expected",
    [
        ("privileged: true", "privileged"),
        ("network_mode: host", "network_mode"),
        ("pid: host", "pid"),
        ("devices: ['/dev/kvm:/dev/kvm']", "devices"),
        ("cap_add: [SYS_ADMIN]", "cap_add"),
        ("use_api_socket: true", "use_api_socket"),
        ("volumes: ['/var/run/docker.sock:/var/run/docker.sock']", "host bind"),
        ("volumes: ['./host-data:/data']", "host bind"),
        ("restart: always", "restart policy"),
    ],
)
def test_dangerous_service_capabilities_are_rejected(
    tmp_path: Path, fragment: str, expected: str
) -> None:
    path = _write(tmp_path, f"services:\n  app:\n    image: alpine\n    {fragment}\n")
    assert any(expected in issue for issue in validate_generated_compose(path, tmp_path))


def test_external_resources_and_escaping_build_context_are_rejected(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
services:
  app:
    build: ../outside
    networks: [prod]
    volumes: [prod-data:/data]
networks:
  prod:
    external: true
volumes:
  prod-data:
    external: true
""",
    )
    issues = validate_generated_compose(path, tmp_path)
    assert any("build context escapes" in issue for issue in issues)
    assert any("custom network" in issue for issue in issues)
    assert any("existing/custom Docker volume" in issue for issue in issues)


def test_factory_secret_and_docker_client_interpolation_are_rejected(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
services:
  app:
    image: alpine
    environment:
      LEAK_ONE: ${ALIEN_API_TOKEN}
      LEAK_TWO: ${DOCKER_HOST}
""",
    )
    issues = validate_generated_compose(path, tmp_path)
    assert any("ALIEN_API_TOKEN" in issue for issue in issues)
    assert any("DOCKER_HOST" in issue for issue in issues)


def test_compose_cli_env_scrubs_factory_secrets_but_keeps_daemon_connection() -> None:
    env = _compose_cli_env(
        {
            "PATH": "/usr/bin",
            "ALIEN_API_TOKEN": "secret",
            "AIFACTORY_REDIS_URL": "redis://:secret@redis/0",
            "DOCKER_HOST": "tcp://docker:2376",
            "DOCKER_TLS_VERIFY": "1",
        }
    )
    assert "ALIEN_API_TOKEN" not in env
    assert "AIFACTORY_REDIS_URL" not in env
    assert env["DOCKER_HOST"] == "tcp://docker:2376"
    assert env["COMPOSE_DISABLE_ENV_FILE"] == "1"


def test_isolation_failure_is_fail_closed(monkeypatch, tmp_path: Path) -> None:
    _write(tmp_path, "services:\n  app:\n    image: alpine\n")
    monkeypatch.setattr(
        "web.backend.services.sandbox_compose_preview.docker_available", lambda: True
    )
    monkeypatch.setattr(
        "web.backend.services.sandbox_compose_preview.prepare_isolation_for_compose",
        lambda _project: (None, None),
    )
    monkeypatch.setattr(
        "web.backend.services.sandbox_compose_preview.preview_network_isolation_enabled",
        lambda: True,
    )

    port, status, project = start_compose_preview(tmp_path, "generated-product")

    assert port is None
    assert status == "compose_isolation_failed"
    assert project is None
