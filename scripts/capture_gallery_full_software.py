#!/usr/bin/env python3
"""
Capture README gallery screenshots for **full_software** products — dashboards, auth, CRUD, settings.

Uses the marketplace **compose sandbox proxy** when available:
  POST /api/sandbox/start/{product_id}
  GET  {base}/api/sandbox/compose/{sandbox_id}/<route>

Env:
  GALLERY_BASE_URL          default http://127.0.0.1:9080
  GALLERY_FS_PRODUCT_ID     one completed full_software product id (required)
  GALLERY_FS_ROUTES         comma-separated paths, default: /,/login,/tasks,/settings
  GALLERY_FS_VIEWPORT_W     default 1440
  GALLERY_FS_VIEWPORT_H     default 900
  GALLERY_FS_WAIT_MS        extra settle time after navigation (default 2500)

Outputs **fullstack-01.webp … fullstack-04.webp** (or N routes) under docs/gallery/.
Requires: factory stack up, AIFACTORY_SANDBOX_COMPOSE_PREVIEW=1 on app, product has docker-compose.yml + UI routes.
"""

from __future__ import annotations

import io
import json
import os
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GALLERY_DIR = REPO_ROOT / "docs" / "gallery"


def _post_json(url: str, body: dict | None = None) -> dict:
    data = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    base = os.environ.get("GALLERY_BASE_URL", "http://127.0.0.1:9080").rstrip("/")
    pid = os.environ.get("GALLERY_FS_PRODUCT_ID", "").strip()
    if not pid:
        raise SystemExit("Set GALLERY_FS_PRODUCT_ID to a full_software product with compose preview.")

    routes_raw = os.environ.get(
        "GALLERY_FS_ROUTES",
        "/,/login,/tasks,/settings",
    )
    routes = [r.strip() or "/" for r in routes_raw.split(",")]

    vw = int(os.environ.get("GALLERY_FS_VIEWPORT_W", "1440"))
    vh = int(os.environ.get("GALLERY_FS_VIEWPORT_H", "900"))
    dwell = int(os.environ.get("GALLERY_FS_WAIT_MS", "2500"))

    from playwright.sync_api import sync_playwright
    from PIL import Image

    GALLERY_DIR.mkdir(parents=True, exist_ok=True)

    data = _post_json(f"{base}/api/sandbox/start/{pid}")
    sandbox_id = data.get("sandbox_id") or ""
    compose = data.get("compose_preview") or {}
    if not sandbox_id.startswith("sandbox-"):
        raise RuntimeError(f"bad sandbox response: {data}")

    if not (compose.get("enabled") or compose.get("proxy_prefix")):
        raise SystemExit(
            "Compose preview inactive — enable AIFACTORY_SANDBOX_COMPOSE_PREVIEW=1 and ensure "
            "docker-compose.yml exists in the product code dir."
        )

    prefix = str(compose.get("proxy_prefix") or f"/api/sandbox/compose/{sandbox_id}/")
    if not prefix.endswith("/"):
        prefix += "/"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        context = browser.new_context(viewport={"width": vw, "height": vh}, device_scale_factor=1)
        page = context.new_page()
        try:
            for i, route in enumerate(routes, start=1):
                path = route.lstrip("/")
                url = f"{base}{prefix}{path}"
                out = GALLERY_DIR / f"fullstack-{i:02d}.webp"
                page.goto(url, wait_until="load", timeout=120_000)
                page.wait_for_timeout(dwell)
                png = page.screenshot(type="png", full_page=False)
                img = Image.open(io.BytesIO(png)).convert("RGB")
                img.save(out, format="WEBP", quality=88, method=6)
                print(f"OK {out.name} ← {url}")
        finally:
            page.close()
            context.close()
            browser.close()

    try:
        stop_url = f"{base}/api/sandbox/stop/{sandbox_id}"
        req = urllib.request.Request(stop_url, method="POST")
        urllib.request.urlopen(req, timeout=30)
    except Exception:
        pass


if __name__ == "__main__":
    main()
