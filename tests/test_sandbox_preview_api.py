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


def test_spa_dist_index(tmp_path: Path):
    assert spa.spa_dist_index(tmp_path) is None
    idx = tmp_path / "frontend" / "dist" / "index.html"
    idx.parent.mkdir(parents=True)
    idx.write_text("<html></html>", encoding="utf-8")
    assert spa.spa_dist_index(tmp_path) == idx


def test_spa_dist_index_accepts_vercel_public(tmp_path: Path):
    idx = tmp_path / "public" / "index.html"
    idx.parent.mkdir(parents=True)
    idx.write_text("<html>relay</html>", encoding="utf-8")
    assert spa.spa_dist_index(tmp_path) == idx


def test_spa_dist_index_prefers_public_over_stale_dist_without_assets(tmp_path: Path):
    """Relay-shaped tree: Vite outDir=public with hashed bundles; leftover dist/index is empty."""
    stale = tmp_path / "dist" / "index.html"
    stale.parent.mkdir(parents=True)
    stale.write_text(
        '<html><script type="module" src="/assets/index.js"></script></html>',
        encoding="utf-8",
    )
    good = tmp_path / "public" / "index.html"
    assets = tmp_path / "public" / "assets"
    assets.mkdir(parents=True)
    (assets / "index-CR_x_y3t.js").write_text("export {}", encoding="utf-8")
    good.write_text(
        '<html><script type="module" src="/assets/index-CR_x_y3t.js"></script></html>',
        encoding="utf-8",
    )
    assert spa.spa_dist_index(tmp_path) == good


def test_spa_dist_index_keeps_frontend_dist_when_assets_present(tmp_path: Path):
    idx = tmp_path / "frontend" / "dist" / "index.html"
    assets = idx.parent / "assets"
    assets.mkdir(parents=True)
    (assets / "index.js").write_text("export {}", encoding="utf-8")
    idx.write_text(
        '<html><script type="module" src="/assets/index.js"></script></html>',
        encoding="utf-8",
    )
    public = tmp_path / "public" / "index.html"
    public.parent.mkdir(parents=True)
    public.write_text("<html>other</html>", encoding="utf-8")
    assert spa.spa_dist_index(tmp_path) == idx


def test_ensure_frontend_dist_skips_npm_when_public_exists(tmp_path: Path, monkeypatch):
    idx = tmp_path / "public" / "index.html"
    idx.parent.mkdir(parents=True)
    idx.write_text("<html>ui</html>", encoding="utf-8")

    def _boom(_code_dir):
        raise AssertionError("must not rebuild when public/index.html exists")

    monkeypatch.setattr(
        "web.backend.services.vercel_fullstack_adapter._try_build_frontend",
        _boom,
    )
    assert spa.ensure_frontend_dist(tmp_path) == idx


def test_ensure_frontend_dist_skips_npm_when_dist_exists(tmp_path: Path, monkeypatch):
    idx = tmp_path / "frontend" / "dist" / "index.html"
    idx.parent.mkdir(parents=True)
    idx.write_text("<html>ui</html>", encoding="utf-8")

    def _boom(_code_dir):
        raise AssertionError("must not rebuild when dist exists")

    monkeypatch.setattr(
        "web.backend.services.vercel_fullstack_adapter._try_build_frontend",
        _boom,
    )
    assert spa.ensure_frontend_dist(tmp_path) == idx


def test_live_preview_opens_spa_file_not_fastapi_root():
    """FastAPI / is {\"message\":\"Sentinel API\"}; the widget lives in dist."""
    path, label = spa.live_preview_iframe_path(
        "sandbox-x",
        dist_rel="frontend/dist/index.html",
        backend_preview_port=49433,
        compose_ok=False,
    )
    assert path == "/api/sandbox/file/sandbox-x/frontend/dist/index.html"
    assert label == "product UI"
    path2, label2 = spa.live_preview_iframe_path(
        "sandbox-x",
        dist_rel=None,
        backend_preview_port=49433,
        compose_ok=False,
    )
    assert path2 == "/api/sandbox/backend/sandbox-x/"
    assert label2 == "FastAPI live app"


def test_preview_api_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AIFACTORY_SANDBOX_PREVIEW_API", raising=False)
    assert spa.preview_api_enabled() is False
    monkeypatch.setenv("AIFACTORY_SANDBOX_PREVIEW_API", "1")
    assert spa.preview_api_enabled() is True
