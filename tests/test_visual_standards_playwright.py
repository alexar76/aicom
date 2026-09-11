"""
Phase 4: Playwright smoke against the golden fixture (tokens, skeleton, labels, toast, mobile nav).

Skipped when Playwright/Chromium is not installed.
"""

from __future__ import annotations

import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "visual_standards_golden"


@pytest.fixture
def golden_url():
    handler = partial(SimpleHTTPRequestHandler, directory=str(FIXTURE_ROOT))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = srv.server_address[1]
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/index.html"
    finally:
        srv.shutdown()
        thread.join(timeout=2)


def test_playwright_visual_standards_golden(golden_url: str):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(golden_url, wait_until="domcontentloaded", timeout=30_000)

        bg = page.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--color-bg').trim()")
        assert bg == "#0f172a"

        assert page.locator(".skeleton-pulse").count() >= 1
        assert page.locator('label[for="email"]').count() == 1
        assert page.locator("#toast-root").count() == 1

        btn = page.locator("#nav-toggle")
        btn.click()
        expanded = btn.get_attribute("aria-expanded")
        assert expanded == "true"

        browser.close()
