#!/usr/bin/env python3
"""
Generate **docs/gallery/fullstack-01.webp … fullstack-04.webp** from the built-in
`packaging/templates/full_stack_fastapi` stack — no running AI pipeline required.

1. `docker compose up -d --build` in the template directory
2. Playwright captures `/`, `/login`, `/tasks`, `/settings` at 1440×900 WebP
3. `docker compose down --volumes --remove-orphans`

Env:
  GALLERY_PACKAGING_PORT   host port (default 9088, must match compose default)
  GALLERY_FS_ROUTES        same as capture_gallery_full_software.py
  GALLERY_FS_WAIT_MS
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = REPO_ROOT / "packaging" / "templates" / "full_stack_fastapi"
GALLERY_DIR = REPO_ROOT / "docs" / "gallery"


def main() -> int:
    port = int(os.environ.get("GALLERY_PACKAGING_PORT", "9088"))
    routes_raw = os.environ.get("GALLERY_FS_ROUTES", "/,/login,/tasks,/settings")
    routes = [r.strip() or "/" for r in routes_raw.split(",")]
    dwell = int(os.environ.get("GALLERY_FS_WAIT_MS", "2500"))

    env = os.environ.copy()
    env["WEB_HOST_PORT"] = str(port)

    if not TEMPLATE.is_dir():
        print("missing template:", TEMPLATE, file=sys.stderr)
        return 1

    compose_file = "docker-compose.yml"
    up = subprocess.run(
        ["docker", "compose", "-f", compose_file, "up", "-d", "--build"],
        cwd=str(TEMPLATE),
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if up.returncode != 0:
        print(up.stderr or up.stdout, file=sys.stderr)
        return 1

    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 120
    ok = False
    try:
        import urllib.request

        while time.time() < deadline:
            try:
                urllib.request.urlopen(base + "/health", timeout=2)
                ok = True
                break
            except Exception:
                time.sleep(0.5)
        if not ok:
            print("timeout waiting for /health", file=sys.stderr)
            return 1

        from playwright.sync_api import sync_playwright
        from PIL import Image

        GALLERY_DIR.mkdir(parents=True, exist_ok=True)
        vw, vh = 1440, 900

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            ctx = browser.new_context(viewport={"width": vw, "height": vh}, device_scale_factor=1)
            page = ctx.new_page()
            try:
                for i, route in enumerate(routes, start=1):
                    path = route if route.startswith("/") else "/" + route
                    url = base.rstrip("/") + path
                    out = GALLERY_DIR / f"fullstack-{i:02d}.webp"
                    page.goto(url, wait_until="load", timeout=120_000)
                    page.wait_for_timeout(dwell)
                    png = page.screenshot(type="png", full_page=False)
                    img = Image.open(io.BytesIO(png)).convert("RGB")
                    img.save(out, format="WEBP", quality=88, method=6)
                    print(f"OK {out.name} ← {url}")
            finally:
                page.close()
                ctx.close()
                browser.close()
    finally:
        down = subprocess.run(
            ["docker", "compose", "-f", compose_file, "down", "--volumes", "--remove-orphans"],
            cwd=str(TEMPLATE),
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if down.returncode != 0:
            print(down.stderr or down.stdout, file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
