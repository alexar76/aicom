"""Customer ZIP delivery contains source, never credential/state files or links."""

from pathlib import Path
import os
from zipfile import ZipFile

import pytest

from web.backend.services.commerce import CommerceService


def test_source_package_excludes_sensitive_runtime_files_and_links(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_DIR", str(tmp_path))
    service = CommerceService(base_dir=tmp_path / "store")
    source = tmp_path / "code" / "prod-test"
    source.mkdir(parents=True)
    safe = {"src/main.py": "print('hello')", "README.md": "setup", ".env.example": "KEY=replace-me", "schema.sql": "CREATE TABLE example(id INT);"}
    private = {".env": "dummy-secret", "backend/.env.production": "dummy-secret", ".git/config": "dummy-credential", "server.key": "dummy-key", "db.sqlite3": "dummy-state", "uploads/note.txt": "dummy-upload", "secrets/token.json": "dummy-token", ".npmrc": "dummy-token"}
    for name, contents in {**safe, **private}.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
    outside = tmp_path / "outside.txt"
    outside.write_text("dummy-outside-file")
    (source / "linked.txt").symlink_to(outside)
    os.link(outside, source / "hardlinked.txt")
    (source / "linked-directory").symlink_to(tmp_path)
    order = {"id": "ord-test", "product_id": "prod-test", "license_key": "test-license"}
    old = service.downloads_dir / "ord-test-prod-test.zip"
    with ZipFile(old, "w") as archive:
        archive.writestr(".env", "dummy-stale-secret")
    result = service.build_download_archive(order)
    assert result != old
    with ZipFile(result) as archive:
        assert set(archive.namelist()) == set(safe) | {"LICENSE.txt"}
        assert archive.read("src/main.py").decode() == safe["src/main.py"]


def test_product_directory_symlink_is_not_a_delivery_root(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_DIR", str(tmp_path))
    service = CommerceService(base_dir=tmp_path / "store")
    (tmp_path / "code").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "code" / "prod-test").symlink_to(outside, target_is_directory=True)
    with pytest.raises(FileNotFoundError):
        service.build_download_archive({"id": "ord-test", "product_id": "prod-test", "license_key": "test"})


@pytest.mark.parametrize("product_id", ["../config", "/tmp", "prod-a/../../config"])
def test_product_delivery_ids_cannot_select_paths(tmp_path, monkeypatch, product_id):
    monkeypatch.setenv("AIFACTORY_DATA_DIR", str(tmp_path))
    service = CommerceService(base_dir=tmp_path / "store")
    with pytest.raises(ValueError):
        service.build_download_archive({"id": "ord-test", "product_id": product_id, "license_key": "test"})
