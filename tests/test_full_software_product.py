"""
full_software packaging + QA hooks: compose/Railway artifacts, FastAPI browser E2E, mobile viewport gate.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from web.backend.services.sandbox_preview_api import detect_fastapi_backend

REPO_ROOT = Path(__file__).resolve().parents[1]
FASTAPI_TEMPLATE = REPO_ROOT / "packaging" / "templates" / "full_stack_fastapi"


@pytest.fixture()
def full_software_product_tree(tmp_path: Path) -> tuple[Path, str]:
    """Minimal data tree: specs + code from the FastAPI packaging template."""
    pid = "fs-packaging-smoke"
    root = tmp_path
    code = root / "code" / pid
    code.mkdir(parents=True)
    for name in (
        "Dockerfile",
        "docker-compose.yml",
        "requirements.txt",
        "nixpacks.toml",
        "Procfile",
        "railway.json",
    ):
        shutil.copy(FASTAPI_TEMPLATE / name, code / name)
    shutil.copytree(FASTAPI_TEMPLATE / "app", code / "app")

    spec_dir = root / "specs" / pid
    spec_dir.mkdir(parents=True)
    spec_dir.joinpath("specification.json").write_text(
        json.dumps(
            {
                "product_name": "FS smoke",
                "delivery_profile": "full_software",
            }
        ),
        encoding="utf-8",
    )
    return root, pid


def test_packaging_template_has_railway_and_compose() -> None:
    """Explicit inventory — CI proves these files exist."""
    for rel in (
        "full_stack_fastapi/nixpacks.toml",
        "full_stack_fastapi/Procfile",
        "full_stack_fastapi/railway.json",
        "full_stack_fastapi/docker-compose.yml",
        "full_stack_fastapi/Dockerfile",
        "full_stack_react_express/nixpacks.toml",
        "full_stack_react_express/Procfile",
        "full_stack_react_express/railway.json",
    ):
        assert (REPO_ROOT / "packaging" / "templates" / rel).is_file(), rel


def test_full_software_tree_has_compose_and_detects_fastapi(full_software_product_tree) -> None:
    root, pid = full_software_product_tree
    code = root / "code" / pid
    assert (code / "docker-compose.yml").is_file()
    assert (code / "nixpacks.toml").is_file()
    assert (code / "railway.json").is_file()
    info = detect_fastapi_backend(code)
    assert info is not None
    assert info.get("module") == "main:app"
    assert (code / "app" / "main.py").is_file()


def test_full_software_browser_e2e_includes_mobile_viewport_gate(
    full_software_product_tree, monkeypatch
) -> None:
    pytest.importorskip("playwright.sync_api", reason="install playwright + chromium for browser E2E")

    from web.backend.services.browser_preview_e2e import run_browser_preview_e2e

    monkeypatch.setenv("AIFACTORY_BROWSER_E2E", "1")
    monkeypatch.setenv("AIFACTORY_BROWSER_E2E_SERVE_MODE", "fastapi")
    monkeypatch.setenv("AIFACTORY_BROWSER_MAX_PAGES", "8")
    monkeypatch.setenv("AIFACTORY_BROWSER_MAX_DEPTH", "3")
    monkeypatch.setenv("AIFACTORY_BROWSER_FS_MOBILE_GATE", "1")
    monkeypatch.setenv("AIFACTORY_BROWSER_FS_MOBILE_ROUTES", "/,/login,/tasks,/settings")

    root, pid = full_software_product_tree
    r = run_browser_preview_e2e(pid, root)
    assert r.get("skipped") is not True
    assert r.get("error") != "playwright_not_installed"
    assert "mobile_viewport_gate" in r
    mg = r.get("mobile_viewport_gate") or {}
    assert mg.get("skipped") is False
    assert mg.get("viewport") == "390x844"
    assert (mg.get("routes_checked") or 0) >= 1
    assert r.get("passed") is True, r.get("issues")
