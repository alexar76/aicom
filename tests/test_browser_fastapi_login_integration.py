"""
Integration: Playwright + uvicorn FastAPI preview + e2e-scenarios login flow.

Skipped when Chromium is not installed (`python -m playwright install chromium`).
CI runs this file in a dedicated workflow job after browser install.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from web.backend.services.browser_preview_e2e import run_browser_preview_e2e

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "minimal_fastapi_login"


@pytest.fixture(scope="module")
def chromium_ready():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            browser.close()
    except Exception as exc:  # pragma: no cover — environment-specific
        pytest.skip(f"Playwright Chromium unavailable: {exc}")


def test_fastapi_preview_login_scenario(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, chromium_ready):
    monkeypatch.setenv("AIFACTORY_BROWSER_E2E_SERVE_MODE", "fastapi")
    monkeypatch.setenv("AIFACTORY_BROWSER_DEEP_CRAWL", "0")
    monkeypatch.setenv("AIFACTORY_VISUAL_DOM_AUDIT", "0")
    monkeypatch.setenv("AIFACTORY_E2E_EMAIL", "ci-user@fixture.local")
    monkeypatch.setenv("AIFACTORY_E2E_PASSWORD", "ci-pass-integration-9")

    pid = "fixture-fastapi-login"
    dest = tmp_path / "code" / pid
    shutil.copytree(FIXTURE_DIR, dest)

    result = run_browser_preview_e2e(pid, tmp_path)

    assert result.get("passed") is True, result
    assert result.get("serve_mode") == "fastapi"
    scen = result.get("scenario_e2e") or {}
    assert scen.get("ran") is True
    assert not scen.get("issues"), scen
    scenarios = scen.get("scenarios") or []
    assert len(scenarios) == 1
    assert scenarios[0].get("name") == "login"
    assert scenarios[0].get("ok") is True
