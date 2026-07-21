"""Capture sandbox hero screenshots for Marketing launch blog posts."""

from __future__ import annotations

import io
import json
import logging
import os
import re
import urllib.request
from pathlib import Path

from core.paths import blog_assets_dir

logger = logging.getLogger(__name__)

FACTORY_SCREENSHOT_TOKEN = "__FACTORY_SCREENSHOT__"
_PROD_ID_RE = re.compile(r"^[a-z0-9]{8,}$")  # at least 8 hex-like chars matching our product-id convention


def _is_safe_asset_name(name: str) -> bool:
    """Validate that a filename looks like a legitimate blog asset (no traversal, no odd chars)."""
    if not name.endswith(".webp"):
        return False
    stem = name[:-5]  # strip ".webp"
    if not stem.startswith("prod-"):
        return False
    return bool(_PROD_ID_RE.match(stem[5:]))


def blog_asset_public_url(product_id: str) -> str:
    return f"/api/blog/assets/{product_id}.webp"


def blog_asset_path(product_id: str) -> Path:
    return blog_assets_dir() / f"{product_id}.webp"


def resolve_capture_base_url(explicit: str | None = None) -> str:
    if explicit and str(explicit).strip():
        return str(explicit).strip().rstrip("/")
    url = (
        os.environ.get("AIFACTORY_BLOG_CAPTURE_BASE_URL", "").strip()
        or os.environ.get("AIFACTORY_SHOWCASE_BASE_URL", "").strip()
        or os.environ.get("AIFACTORY_PUBLIC_URL", "").strip()
        or "http://127.0.0.1:9080"
    ).rstrip("/")
    if Path("/.dockerenv").is_file():
        for host in ("127.0.0.1", "localhost"):
            url = url.replace(f"http://{host}:9080", f"http://{host}:8080")
            url = url.replace(f"https://{host}:9080", f"https://{host}:8080")
    return url


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


def capture_blog_hero(product_id: str, *, base_url: str | None = None) -> str | None:
    """Screenshot generated landing HTML; returns public URL path or None on failure."""
    pid = str(product_id or "").strip()
    if not pid:
        return None
    base = resolve_capture_base_url(base_url)
    index_rel = os.environ.get("BLOG_CAPTURE_INDEX_RELPATH", "index.html").strip().lstrip("/")
    try:
        data = _post_json(f"{base}/api/sandbox/start/{pid}")
        sandbox_id = str(data.get("sandbox_id") or "")
        if not sandbox_id.startswith("sandbox-"):
            logger.warning("blog screenshot: bad sandbox response for %s", pid)
            return None
        url = f"{base}/api/sandbox/file/{sandbox_id}/{index_rel}"
        from playwright.sync_api import sync_playwright
        from PIL import Image

        out = blog_asset_path(pid)
        out.parent.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            context = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
            page = context.new_page()
            try:
                page.goto(url, wait_until="load", timeout=120_000)
                page.wait_for_timeout(2000)
                png = page.screenshot(type="png", full_page=False)
            finally:
                page.close()
                context.close()
                browser.close()
        img = Image.open(io.BytesIO(png)).convert("RGB")
        img.save(out, format="WEBP", quality=88, method=6)
        logger.info("blog screenshot: saved %s for %s", out.name, pid)
        return blog_asset_public_url(pid)
    except Exception:
        logger.debug("blog screenshot capture failed for %s", pid, exc_info=True)
        existing = blog_asset_path(pid)
        if existing.is_file() and existing.stat().st_size > 512:
            return blog_asset_public_url(pid)
        return None


def asset_file_for_request(filename: str) -> Path | None:
    name = Path(str(filename or "")).name
    if not _is_safe_asset_name(name):
        return None
    path = blog_assets_dir() / name
    return path if path.is_file() else None
