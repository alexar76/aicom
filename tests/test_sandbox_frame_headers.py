"""Sandbox Live Preview: iframe children must allow same-origin embedding."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.backend.middleware.sandbox_opaque_cors import (
    sandbox_opaque_cors_path,
    sandbox_opaque_origin_cors,
)


def test_sandbox_embed_paths_detected():
    from web.backend.main import _sandbox_preview_embed_path, _sandbox_relaxed_security_path

    assert _sandbox_preview_embed_path("/api/sandbox/file/sb-1/index.html")
    assert _sandbox_preview_embed_path("/api/sandbox/compose/sb-1/")
    assert _sandbox_preview_embed_path("/api/sandbox/backend/sb-1/api/health")
    assert not _sandbox_preview_embed_path("/api/sandbox/view/sb-1")
    assert _sandbox_relaxed_security_path("/api/sandbox/view/sb-1")
    assert not _sandbox_relaxed_security_path("/api/health")


def test_opaque_cors_paths_exclude_viewer_and_admin():
    assert sandbox_opaque_cors_path("/api/sandbox/file/sb-1/index.html")
    assert sandbox_opaque_cors_path("/api/sandbox/backend/sb-1/api/health")
    assert sandbox_opaque_cors_path("/api/v1/sandbox/compose/sb-1/")
    assert not sandbox_opaque_cors_path("/api/sandbox/view/sb-1")
    assert not sandbox_opaque_cors_path("/api/admin/settings")
    assert not sandbox_opaque_cors_path("/api/health")


def test_sandbox_file_route_allows_sameorigin_framing():
    from web.backend.main import app

    with TestClient(app) as client:
        r = client.get("/api/sandbox/file/test-sandbox-id/index.html")
    # Sandbox not running — 404 is fine; headers must not block iframe on success paths.
    assert r.status_code in (404, 200)
    assert r.headers.get("X-Frame-Options") == "SAMEORIGIN"


def test_opaque_origin_gets_null_cors_without_credentials():
    """Mini-app: opaque iframe CORS must not require full factory boot."""
    mini = FastAPI()
    mini.middleware("http")(sandbox_opaque_origin_cors)

    @mini.get("/api/sandbox/file/{sid}/index.html")
    def file_ok(sid: str):
        return {"ok": True, "sid": sid}

    @mini.get("/api/sandbox/backend/{sid}/api/health")
    def backend_ok(sid: str):
        return {"ok": True}

    @mini.get("/api/health")
    def health():
        return {"ok": True}

    with TestClient(mini) as client:
        r = client.get(
            "/api/sandbox/file/test-sandbox-id/index.html",
            headers={"Origin": "null"},
        )
        preflight = client.options(
            "/api/sandbox/backend/test-sandbox-id/api/health",
            headers={
                "Origin": "null",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-Sandbox-Preview-Token",
            },
        )
        other = client.get("/api/health", headers={"Origin": "null"})

    assert r.status_code == 200
    assert r.headers.get("Access-Control-Allow-Origin") == "null"
    assert "access-control-allow-credentials" not in {
        k.lower() for k in r.headers.keys()
    }
    assert preflight.status_code == 204
    assert preflight.headers.get("Access-Control-Allow-Origin") == "null"
    assert "X-Sandbox-Preview-Token" in (
        preflight.headers.get("Access-Control-Allow-Headers") or ""
    )
    # Must not open the whole API to opaque documents.
    assert other.headers.get("Access-Control-Allow-Origin") != "null"


def test_sandbox_viewer_csp_allows_iframe_child():
    from web.backend.services.sandbox_static_rewrite import SANDBOX_VIEWER_CSP

    assert "frame-src 'self'" in SANDBOX_VIEWER_CSP
    assert "object-src 'none'" in SANDBOX_VIEWER_CSP
    assert "default-src 'none'" not in SANDBOX_VIEWER_CSP


def test_sandbox_html_csp_blocks_object_and_script_attrs():
    from web.backend.services.sandbox_static_rewrite import SANDBOX_HTML_CSP

    assert "object-src 'none'" in SANDBOX_HTML_CSP
    assert "script-src-attr 'none'" in SANDBOX_HTML_CSP
