"""product_has_code must see source on disk even when a patch wiped the manifest file list."""

from __future__ import annotations

import json
from pathlib import Path

from web.backend.services.product_code_presence import (
    preserve_manifest_file_entries,
    product_has_code,
)


def test_empty_manifest_still_true_when_source_exists(tmp_path: Path):
    """Relay's storefront card: files:[] after a docs-only mesh patch, tree intact."""
    root = tmp_path / "prod-relay"
    (root / "backend" / "app").mkdir(parents=True)
    (root / "backend" / "app" / "main.py").write_text("app = None\n", encoding="utf-8")
    (root / "code_manifest.json").write_text(
        json.dumps(
            {
                "product_id": "prod-relay",
                "files": [],
                "documentation": "Fixed mesh_contract_violation only.",
            }
        ),
        encoding="utf-8",
    )
    assert product_has_code(root) is True


def test_manifest_path_that_exists_is_enough(tmp_path: Path):
    root = tmp_path / "prod"
    root.mkdir()
    (root / "index.html").write_text("<html></html>", encoding="utf-8")
    (root / "code_manifest.json").write_text(
        json.dumps({"files": [{"path": "index.html"}]}),
        encoding="utf-8",
    )
    assert product_has_code(root) is True


def test_stale_manifest_paths_fall_back_to_disk(tmp_path: Path):
    root = tmp_path / "prod"
    (root / "frontend").mkdir(parents=True)
    (root / "frontend" / "App.tsx").write_text("export {}\n", encoding="utf-8")
    (root / "code_manifest.json").write_text(
        json.dumps({"files": [{"path": "gone/old.html"}]}),
        encoding="utf-8",
    )
    assert product_has_code(root) is True


def test_empty_tree_is_not_code(tmp_path: Path):
    root = tmp_path / "prod"
    root.mkdir()
    (root / "code_manifest.json").write_text(
        json.dumps({"files": []}),
        encoding="utf-8",
    )
    (root / "README.md").write_text("# hi\n", encoding="utf-8")
    assert product_has_code(root) is False


def test_preserve_prior_manifest_skips_deleted_and_strips_content():
    prior = [
        {"path": "backend/app/main.py", "content": "x" * 100},
        {"path": "frontend/index.html", "full_path": "/tmp/x"},
        {"path": "scratch.tmp"},
    ]
    kept = preserve_manifest_file_entries(prior, deleted_paths={"scratch.tmp"})
    assert kept == [
        {"path": "backend/app/main.py", "preserved": True},
        {"path": "frontend/index.html", "preserved": True},
    ]


def test_storefront_and_dev_wire_the_shared_helper():
    """Structural: grid gate and patch writer must not re-grow a private files:[] check."""
    root = Path(__file__).resolve().parents[1]
    products = (root / "web" / "backend" / "api" / "products.py").read_text(encoding="utf-8")
    assert "from web.backend.services.product_code_presence import product_has_code" in products
    assert 'if not files:\n        return False' not in products
    dev = (root / "agents" / "dev.py").read_text(encoding="utf-8")
    assert "preserve_manifest_file_entries" in dev
    assert "Preserved" in dev and "prior manifest" in dev
