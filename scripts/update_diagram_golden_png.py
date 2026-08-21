#!/usr/bin/env python3
"""Render tests/fixtures/diagram_ok.html and write tests/golden/diagram_ok.png for visual regression."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "diagram_ok.html"
OUT = ROOT / "tests" / "golden" / "diagram_ok.png"


def main() -> int:
    if not FIXTURE.is_file():
        print(f"missing fixture {FIXTURE}", file=sys.stderr)
        return 2
    OUT.parent.mkdir(parents=True, exist_ok=True)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("install playwright: pip install playwright && playwright install chromium", file=sys.stderr)
        return 3
    uri = FIXTURE.resolve().as_uri()
    with sync_playwright() as sp:
        browser = sp.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
        page = browser.new_page(viewport={"width": 640, "height": 480})
        page.goto(uri, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(400)
        page.screenshot(path=str(OUT), full_page=False)
        browser.close()
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
