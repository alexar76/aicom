"""Desktop app factory product type — delivery profile, gates, taxonomy."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.delivery_profile import DESKTOP_APP, normalize_delivery_profile
from agents.dev_delivery import DeliveryMode, infer_delivery_mode, validate_saved_files
from agents.product_profile import infer_delivery_profile
from web.backend.services.desktop_product import (
    assess_desktop_product_demo,
    desktop_storefront_ready,
    detect_desktop_framework,
    infer_category_for_new_product,
)


def test_normalize_desktop_delivery_profile():
    assert normalize_delivery_profile("desktop_app") == DESKTOP_APP
    assert normalize_delivery_profile("electron_app") == DESKTOP_APP
    assert normalize_delivery_profile("full_software") != DESKTOP_APP


def test_infer_delivery_profile_desktop_idea():
    assert infer_delivery_profile(None, "Tauri desktop app for offline PDF review with system tray") == DESKTOP_APP


def test_infer_delivery_mode_desktop():
    spec = {"delivery_profile": "desktop_app", "product_name": "Local Tool"}
    assert infer_delivery_mode(None, spec, DESKTOP_APP) == DeliveryMode.DESKTOP_APP


def test_validate_tauri_files():
    ok, err = validate_saved_files(
        DeliveryMode.DESKTOP_APP,
        ["src-tauri/Cargo.toml", "src-tauri/src/main.rs", "ui/index.html", "README.md"],
    )
    assert ok, err


def test_detect_tauri_framework(tmp_path: Path):
    root = tmp_path / "prod-x"
    (root / "src-tauri").mkdir(parents=True)
    (root / "src-tauri" / "Cargo.toml").write_text("[package]\nname='x'\n", encoding="utf-8")
    (root / "ui").mkdir()
    (root / "ui" / "index.html").write_text("<html></html>", encoding="utf-8")
    (root / "README.md").write_text("# Desktop\n\nBuild with cargo tauri dev\n" * 3, encoding="utf-8")
    (root / "code_manifest.json").write_text(json.dumps({"files": [{"path": "ui/index.html"}]}), encoding="utf-8")
    assert detect_desktop_framework(root) == "tauri"
    ok, reasons = desktop_storefront_ready("prod-x", code_root=root)
    assert ok, reasons


def test_assess_desktop_demo(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))
    pid = "prod-desktop-test"
    root = tmp_path / "data" / "code" / pid
    (root / "src-tauri").mkdir(parents=True)
    (root / "src-tauri" / "Cargo.toml").write_text("[package]\nname='x'\n", encoding="utf-8")
    (root / "ui").mkdir()
    (root / "ui" / "index.html").write_text("<html><body>Desktop UI</body></html>", encoding="utf-8")
    (root / "README.md").write_text("# Build\n\n`cargo tauri dev`\n" * 4, encoding="utf-8")
    (root / "code_manifest.json").write_text(json.dumps({"files": [{"path": "ui/index.html"}]}), encoding="utf-8")
    report = assess_desktop_product_demo(pid, spec={"delivery_profile": "desktop_app"}, data_root=tmp_path / "data")
    assert report["desktop_ready"] is True
    assert report["product_kind"] == "desktop_app"


def test_infer_category_desktop():
    assert infer_category_for_new_product("Electron desktop CRM", delivery_profile=DESKTOP_APP) == "desktop"


def test_marketplace_taxonomy_desktop_alias():
    from marketplace_taxonomy import slug_to_marketplace_category

    assert slug_to_marketplace_category("desktop_app") == "desktop"
    assert slug_to_marketplace_category("tauri") == "desktop"
