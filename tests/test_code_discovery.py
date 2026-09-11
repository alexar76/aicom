"""Tests for product code path filtering."""

from __future__ import annotations

import tempfile
from pathlib import Path

from core.code_discovery import (
    copytree_ignore,
    iter_product_files,
    should_skip_code_path,
)


def test_should_skip_sandbox_and_vendor_paths():
    p = Path("/app/data/code/prod-x/.aicom_sandbox/e2e/preview-venv/lib/python3.12/site-packages/foo.py")
    assert should_skip_code_path(p) is True
    assert should_skip_code_path(Path("/app/data/code/prod-x/backend/main.py")) is False


def test_iter_product_files_skips_preview_venv():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "main.py").write_text("print('ok')\n", encoding="utf-8")
        venv = root / ".aicom_sandbox" / "sb" / "preview-venv" / "lib" / "site-packages"
        venv.mkdir(parents=True)
        (venv / "test_vendor.py").write_text("def test_x(): pass\n", encoding="utf-8")
        found = {p.name for p in iter_product_files(root, "*.py")}
        assert found == {"main.py"}


def test_methodology_and_demo_quality_skip_sandbox_blobs(tmp_path):
    """QA used to concatenate .aicom_sandbox venvs into RAM and OOM the 4GiB worker."""
    from web.backend.services.demo_quality import _iter_text_artifacts
    from web.backend.services.methodology_review import _iter_code_artifacts

    (tmp_path / "index.html").write_text("<html><body>ok</body></html>\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('ok')\n", encoding="utf-8")
    vendor = tmp_path / ".aicom_sandbox" / "e2e" / "lib" / "site-packages"
    vendor.mkdir(parents=True)
    (vendor / "huge.py").write_text("x = '" + ("n" * 200_000) + "'\n", encoding="utf-8")

    demo_rels = {rel for rel, _p, _t in _iter_text_artifacts(tmp_path)}
    meth_rels = {rel for rel, _t in _iter_code_artifacts(tmp_path)}
    assert "main.py" in meth_rels
    assert "index.html" in demo_rels
    assert not any("huge.py" in r or ".aicom_sandbox" in r for r in demo_rels)
    assert not any("huge.py" in r or ".aicom_sandbox" in r for r in meth_rels)


def test_copytree_ignore_drops_vendor_dirs():
    ignored = copytree_ignore("/tmp", ["main.py", "node_modules", "preview-venv", "src"])
    assert ignored == ["node_modules", "preview-venv"]
