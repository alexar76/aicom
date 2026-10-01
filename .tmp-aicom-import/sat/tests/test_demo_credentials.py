"""Tests for sandbox demo password default detection."""

from __future__ import annotations

import pytest

from web.backend.services.demo_credentials import (
    DEFAULT_SANDBOX_DEMO_PASSWORD,
    DOCKER_COMPOSE_DEFAULT_SANDBOX_DEMO_PASSWORD,
    effective_sandbox_demo_password_for_compose,
    sandbox_demo_password_uses_default,
)


def test_uses_default_when_env_unset(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delenv("AIFACTORY_SANDBOX_DEMO_PASSWORD", raising=False)
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    assert sandbox_demo_password_uses_default() is True


def test_uses_default_when_env_matches_literal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFACTORY_SANDBOX_DEMO_PASSWORD", DEFAULT_SANDBOX_DEMO_PASSWORD)
    assert sandbox_demo_password_uses_default() is True


def test_uses_default_when_compose_legacy_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "AIFACTORY_SANDBOX_DEMO_PASSWORD",
        DOCKER_COMPOSE_DEFAULT_SANDBOX_DEMO_PASSWORD,
    )
    assert sandbox_demo_password_uses_default() is True


def test_not_default_when_custom(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFACTORY_SANDBOX_DEMO_PASSWORD", "unique-secret-not-default")
    assert sandbox_demo_password_uses_default() is False


def test_effective_password_prefers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFACTORY_SANDBOX_DEMO_PASSWORD", "from-env")
    assert effective_sandbox_demo_password_for_compose() == "from-env"


def test_effective_password_from_file(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    import web.backend.services.demo_credentials as dc

    monkeypatch.delenv("AIFACTORY_SANDBOX_DEMO_PASSWORD", raising=False)
    pw_file = tmp_path / "sandbox_demo_password"
    pw_file.write_text("file-generated-secret", encoding="utf-8")
    monkeypatch.setattr(dc, "_SANDBOX_PW_FILE", pw_file)
    assert dc.effective_sandbox_demo_password_for_compose() == "file-generated-secret"


def test_whitespace_trim(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFACTORY_SANDBOX_DEMO_PASSWORD", f"  {DEFAULT_SANDBOX_DEMO_PASSWORD}  ")
    assert sandbox_demo_password_uses_default() is True
