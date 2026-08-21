"""FastAPI GET / is JSON; the widget lives in frontend/dist. Overlay that for QA."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.backend.services import sandbox_preview_api as spa
from web.backend.services.spa_preview_asgi import resolve_spa_file, should_passthrough_to_api, wrap_asgi


def test_api_paths_passthrough():
    assert should_passthrough_to_api("/api/advisory") is True
    assert should_passthrough_to_api("/api") is True
    assert should_passthrough_to_api("/openapi.json") is True
    assert should_passthrough_to_api("/docs") is True
    assert should_passthrough_to_api("/") is False
    assert should_passthrough_to_api("/login") is False
    assert should_passthrough_to_api("/operator") is False
    assert should_passthrough_to_api("/assets/index.js") is False


def test_resolve_spa_file_client_routes_and_assets(tmp_path: Path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html><h1>Sentinel</h1></html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("ok", encoding="utf-8")
    assert resolve_spa_file(dist, "/").name == "index.html"
    assert resolve_spa_file(dist, "/login").name == "index.html"
    assert resolve_spa_file(dist, "/assets/app.js").name == "app.js"
    assert resolve_spa_file(dist, "/missing.png") is None
    escaped = resolve_spa_file(dist, "/../../etc/passwd")
    assert escaped is not None and escaped.name == "index.html"


def test_wrap_serves_spa_not_json_stub(tmp_path: Path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html><h1>Sentinel</h1></html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    inner = FastAPI()

    @inner.get("/")
    def root():
        return {"message": "Sentinel API"}

    @inner.get("/api/health")
    def health():
        return {"ok": True}

    client = TestClient(wrap_asgi(inner, dist))
    home = client.get("/")
    assert home.status_code == 200
    assert "Sentinel" in home.text
    assert "Sentinel API" not in home.text
    login = client.get("/login")
    assert "<h1>Sentinel</h1>" in login.text
    assert client.get("/api/health").json() == {"ok": True}
    assert client.get("/assets/app.js").text == "console.log(1)"


def test_prepare_spa_preview_writes_overlay(tmp_path: Path):
    idx = tmp_path / "frontend" / "dist" / "index.html"
    idx.parent.mkdir(parents=True)
    idx.write_text("<html></html>", encoding="utf-8")
    pp, target = spa.prepare_spa_preview_uvicorn(
        sandbox_id="sandbox-spa",
        code_dir=tmp_path,
        inner_module="app.main:app",
        dist_index=idx,
    )
    assert target == "aicom_spa_preview:app"
    overlay = Path(pp)
    assert (overlay / "aicom_spa_preview.py").is_file()
    assert (overlay / "spa_preview_asgi.py").is_file()
    text = (overlay / "aicom_spa_preview.py").read_text(encoding="utf-8")
    assert "app.main" in text
    assert "wrap_asgi" in text


def test_start_fastapi_preview_targets_spa_overlay(tmp_path: Path, monkeypatch):
    backend = tmp_path / "backend"
    app_pkg = backend / "app"
    app_pkg.mkdir(parents=True)
    (app_pkg / "__init__.py").write_text("", encoding="utf-8")
    (app_pkg / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n",
        encoding="utf-8",
    )
    idx = tmp_path / "frontend" / "dist" / "index.html"
    idx.parent.mkdir(parents=True)
    idx.write_text("<html><h1>Sentinel</h1></html>", encoding="utf-8")

    seen: dict = {}

    class _Proc:
        stderr = None

        def terminate(self):
            return None

        def wait(self, timeout=None):
            return 0

        def kill(self):
            return None

    def fake_popen(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["env"] = kwargs.get("env")
        seen["cwd"] = kwargs.get("cwd")
        return _Proc()

    monkeypatch.setattr(spa.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(spa, "wait_port_open", lambda *a, **k: True)
    monkeypatch.setattr(spa, "pick_loopback_port", lambda: 59999)
    monkeypatch.setattr(
        spa,
        "build_fastapi_preview_env",
        lambda **k: ({"PYTHONPATH": str(backend), **dict(os.environ)}, {"preview_python": sys.executable}),
    )

    port, proc, status = spa.start_fastapi_preview(sandbox_id="s1", code_dir=tmp_path)
    assert status == "ok"
    assert port == 59999
    assert "aicom_spa_preview:app" in seen["cmd"]
    assert "spa_overlay" in seen["env"]["PYTHONPATH"]
    assert seen["cwd"] == str(backend)
    assert proc is not None


def test_start_fastapi_preview_skips_overlay_without_dist(tmp_path: Path, monkeypatch):
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n",
        encoding="utf-8",
    )
    seen: dict = {}

    class _Proc:
        stderr = None

        def terminate(self):
            return None

        def wait(self, timeout=None):
            return 0

        def kill(self):
            return None

    monkeypatch.setattr(spa.subprocess, "Popen", lambda cmd, **kwargs: seen.update(cmd=cmd) or _Proc())
    monkeypatch.setattr(spa, "wait_port_open", lambda *a, **k: True)
    monkeypatch.setattr(spa, "pick_loopback_port", lambda: 59998)
    monkeypatch.setattr(
        spa,
        "build_fastapi_preview_env",
        lambda **k: ({"PYTHONPATH": str(backend)}, {"preview_python": sys.executable}),
    )

    _port, _proc, status = spa.start_fastapi_preview(sandbox_id="s2", code_dir=tmp_path)
    assert status == "ok"
    assert "main:app" in seen["cmd"]
    assert "aicom_spa_preview:app" not in seen["cmd"]
