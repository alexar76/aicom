"""Sandbox Live Preview: iframe children must allow same-origin embedding."""

from web.backend.main import _sandbox_preview_embed_path, _sandbox_relaxed_security_path


def test_sandbox_embed_paths_detected():
    assert _sandbox_preview_embed_path("/api/sandbox/file/sb-1/index.html")
    assert _sandbox_preview_embed_path("/api/sandbox/compose/sb-1/")
    assert _sandbox_preview_embed_path("/api/sandbox/backend/sb-1/api/health")
    assert not _sandbox_preview_embed_path("/api/sandbox/view/sb-1")
    assert _sandbox_relaxed_security_path("/api/sandbox/view/sb-1")
    assert not _sandbox_relaxed_security_path("/api/health")


def test_sandbox_file_route_allows_sameorigin_framing():
    from fastapi.testclient import TestClient

    from web.backend.main import app

    with TestClient(app) as client:
        r = client.get("/api/sandbox/file/test-sandbox-id/index.html")
    # Sandbox not running — 404 is fine; headers must not block iframe on success paths.
    assert r.status_code in (404, 200)
    assert r.headers.get("X-Frame-Options") == "SAMEORIGIN"


def test_sandbox_viewer_csp_allows_iframe_child():
    from web.backend.services.sandbox_static_rewrite import SANDBOX_VIEWER_CSP

    assert "frame-src 'self'" in SANDBOX_VIEWER_CSP
    assert "object-src 'none'" in SANDBOX_VIEWER_CSP
    assert "default-src 'none'" not in SANDBOX_VIEWER_CSP


def test_sandbox_html_csp_blocks_object_and_script_attrs():
    from web.backend.services.sandbox_static_rewrite import SANDBOX_HTML_CSP

    assert "object-src 'none'" in SANDBOX_HTML_CSP
    assert "script-src-attr 'none'" in SANDBOX_HTML_CSP
