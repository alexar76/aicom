#!/usr/bin/env python3
"""
Capture README hero gallery screenshots — **generated landing HTML only** (no sandbox viewer chrome).

For each product: `POST /api/sandbox/start/{id}`, then screenshot
`/api/sandbox/file/{sandbox_id}/{GALLERY_INDEX_RELPATH}` (same document as the iframe in the viewer).

Env:
  GALLERY_BASE_URL       default http://127.0.0.1:9080
  GALLERY_PRODUCT_IDS    comma-separated override (5 or 6 ids)
  GALLERY_INDEX_RELPATH  path under product code dir (default index.html)
"""

from __future__ import annotations

import io
import json
import os
import urllib.request
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
GALLERY_DIR = REPO_ROOT / "docs" / "gallery"

DEFAULT_IDS = (
    "prod-6d91fbf08e22",
    "prod-ebb14acd7f7c",
    "prod-00b81f6b99f2",
    "prod-83de9f2172f3",
    "prod-da444f695cbe",
)


def _post_json(url: str, body: dict | None = None) -> dict:
    data = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    base = os.environ.get("GALLERY_BASE_URL", "http://127.0.0.1:9080").rstrip("/")
    index_rel = os.environ.get("GALLERY_INDEX_RELPATH", "index.html").strip().lstrip("/")
    raw = os.environ.get("GALLERY_PRODUCT_IDS", "").strip()
    if raw:
        ids = tuple(x.strip() for x in raw.split(",") if x.strip())
    else:
        ids = DEFAULT_IDS
    if len(ids) not in (5, 6):
        raise SystemExit(f"Need 5 or 6 product ids, got {len(ids)}: {ids}")

    from playwright.sync_api import sync_playwright

    GALLERY_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=1,
        )
        page = context.new_page()
        try:
            for i, pid in enumerate(ids, start=1):
                out = GALLERY_DIR / f"landing-{i:02d}.webp"
                data = _post_json(f"{base}/api/sandbox/start/{pid}")
                sandbox_id = data.get("sandbox_id") or ""
                if not sandbox_id or not str(sandbox_id).startswith("sandbox-"):
                    raise RuntimeError(f"bad sandbox response (missing sandbox_id): {data}")
                # Raw static/HTML route — no sidebar/header viewer UI
                url = f"{base}/api/sandbox/file/{sandbox_id}/{index_rel}"
                page.goto(url, wait_until="load", timeout=120_000)
                page.wait_for_timeout(2000)
                png = page.screenshot(type="png", full_page=False)
                img = Image.open(io.BytesIO(png)).convert("RGB")
                img.save(out, format="WEBP", quality=88, method=6)
                print(f"OK {out.name} ← {pid} ({url})")
        finally:
            page.close()
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
