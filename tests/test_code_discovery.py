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


def test_copytree_ignore_drops_vendor_dirs():
    ignored = copytree_ignore("/tmp", ["main.py", "node_modules", "preview-venv", "src"])
    assert ignored == ["node_modules", "preview-venv"]
