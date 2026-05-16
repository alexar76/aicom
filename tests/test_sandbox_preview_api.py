"""Unit tests for sandbox FastAPI preview detection (no uvicorn spawn)."""

from __future__ import annotations

from pathlib import Path

from web.backend.services import sandbox_preview_api as spa


def test_detect_fastapi_backend_backend_main(tmp_path: Path):
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/')\ndef r(): return {}\n",
        encoding="utf-8",
    )
    info = spa.detect_fastapi_backend(tmp_path)
    assert info is not None
    assert info["cwd"] == backend
    assert info["module"] == "main:app"


def test_detect_fastapi_backend_nested_app_package(tmp_path: Path):
    backend = tmp_path / "backend"
    app_pkg = backend / "app"
    app_pkg.mkdir(parents=True)
    (app_pkg / "__init__.py").write_text("", encoding="utf-8")
    (app_pkg / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n",
        encoding="utf-8",
    )
    info = spa.detect_fastapi_backend(tmp_path)
    assert info is not None
    assert info["cwd"] == backend
    assert info["module"] == "app.main:app"


def test_detect_fastapi_backend_negative(tmp_path: Path):
    (tmp_path / "readme.txt").write_text("hello")
    assert spa.detect_fastapi_backend(tmp_path) is None


def test_preview_api_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AIFACTORY_SANDBOX_PREVIEW_API", raising=False)
    assert spa.preview_api_enabled() is False
    monkeypatch.setenv("AIFACTORY_SANDBOX_PREVIEW_API", "1")
    assert spa.preview_api_enabled() is True
