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
