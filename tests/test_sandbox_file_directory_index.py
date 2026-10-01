"""Sandbox file route: a directory URL serves its index.html.

Under the injected ``<base href=".../frontend/dist/">`` a hash link or a reload lands on the
directory itself; answering ``File not found: frontend/dist`` blanked the Sentinel preview.
"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.backend.api import sandbox as sandbox_api

SID = "sandbox-dirindex"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    dist = tmp_path / "frontend" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        '<!DOCTYPE html><html><head><script type="module" src="/assets/app.js"></script>'
        '</head><body><a href="#/login">Login</a></body></html>',
        encoding="utf-8",
    )
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    monkeypatch.setattr(
        sandbox_api,
        "_lookup_sandbox",
        lambda sid: {"status": "running", "product_id": "prod-x"} if sid == SID else None,
    )
    monkeypatch.setattr(sandbox_api, "_get_product_code_dir", lambda pid: tmp_path)
    app = FastAPI()
    app.include_router(sandbox_api.router)
    with TestClient(app) as c:
        yield c, tmp_path


@pytest.mark.parametrize("path", ["frontend/dist/", "frontend/dist"])
def test_directory_serves_index_with_directory_base(client, path):
    c, _ = client
    r = c.get(f"/api/sandbox/file/{SID}/{path}")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/html")
    # base must be the directory even without a trailing slash, or ./assets/… 404s
    assert f'/api/sandbox/file/{SID}/frontend/dist/"' in r.text
    assert "aicom-sandbox-fragment-links" in r.text
    assert "aicom-sandbox-storage-shim" in r.text
    assert 'src="./assets/app.js"' in r.text


def test_directory_without_index_is_still_404(client):
    c, root = client
    (root / "docs").mkdir()
    r = c.get(f"/api/sandbox/file/{SID}/docs/")
    assert r.status_code == 404


def test_symlinked_directory_index_is_not_followed(client, tmp_path_factory):
    c, root = client
    outside = tmp_path_factory.mktemp("outside") / "secret.html"
    outside.write_text("<html>secret</html>", encoding="utf-8")
    (root / "linked").mkdir()
    (root / "linked" / "index.html").symlink_to(outside)
    r = c.get(f"/api/sandbox/file/{SID}/linked/")
    assert r.status_code in (403, 404)
    assert "secret" not in r.text
