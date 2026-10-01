#!/usr/bin/env python3
"""Capture a short sandbox walkthrough clip for product showcase gallery."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

BASE = os.environ.get("DEMO_VIDEO_BASE_URL", "http://127.0.0.1:9080").rstrip("/")
PRODUCT_ID = os.environ.get("DEMO_VIDEO_SANDBOX_PRODUCT_ID", "").strip()
OUT = Path(os.environ.get("DEMO_VIDEO_OUT", "docs/gallery/recordings"))
VIEW_W = int(os.environ.get("DEMO_VIDEO_VIEWPORT_W", "1280"))
VIEW_H = int(os.environ.get("DEMO_VIDEO_VIEWPORT_H", "720"))


def main() -> int:
    if not PRODUCT_ID:
        print("DEMO_VIDEO_SANDBOX_PRODUCT_ID required", file=sys.stderr)
        return 2
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        meta = OUT / f"showcase-{PRODUCT_ID}.json"
        OUT.mkdir(parents=True, exist_ok=True)
        meta.write_text(
            json.dumps(
                {
                    "product_id": PRODUCT_ID,
                    "preview_url": f"{BASE}/api/sandbox/preview/{PRODUCT_ID}/",
                    "captured_at": time.time(),
                    "note": "playwright not installed — stub metadata only",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return 0

    url = f"{BASE}/api/sandbox/preview/{PRODUCT_ID}/"
    OUT.mkdir(parents=True, exist_ok=True)
    out_file = OUT / f"showcase-{PRODUCT_ID}.webm"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": VIEW_W, "height": VIEW_H},
            record_video_dir=str(OUT),
            record_video_size={"width": VIEW_W, "height": VIEW_H},
        )
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=120_000)
        page.wait_for_timeout(2500)
        for _ in range(4):
            page.mouse.wheel(0, 400)
            page.wait_for_timeout(600)
        page.wait_for_timeout(1500)
        video = page.video
        context.close()
        browser.close()
        if video:
            path = video.path()
            if path and Path(path).exists():
                Path(path).replace(out_file)
    print(json.dumps({"ok": True, "product_id": PRODUCT_ID, "file": str(out_file)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
