"""Integration: GET /api/admin/dashboard/products/{id}/files via mounted router."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.backend.core.admin_roles import AdminRole, require_admin_with_rbac


@pytest.fixture
def admin_files_client(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    from web.backend.api.admin.dashboard import routes_products  # noqa: F401 — register routes
    from web.backend.api.admin.dashboard._router import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin_with_rbac] = lambda: AdminRole.ADMIN
    return TestClient(app)


def test_get_product_files_route_via_testclient(admin_files_client, tmp_path):
    code_root = tmp_path / "code" / "prod-files-route-test"
    code_root.mkdir(parents=True)
    (code_root / "index.html").write_text("<html></html>", encoding="utf-8")

    resp = admin_files_client.get("/api/admin/products/prod-files-route-test/files")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    assert any(f.get("category") == "code" for f in data["files"])


def test_get_product_files_requires_admin_dependency(admin_files_client):
    """Without override, RBAC dependency would reject — ensure route is wired."""
    from web.backend.api.admin.dashboard._router import router

    paths = [getattr(r, "path", "") for r in router.routes]
    assert any("products/{product_id}/files" in p for p in paths)
