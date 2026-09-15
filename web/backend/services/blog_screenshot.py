"""Capture hero screenshots for Marketing launch blog posts."""

from __future__ import annotations

import io
import json
import logging
import os
import re
import urllib.error
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


def live_capture_page_urls(product_id: str) -> list[str]:
    """Public pages worth a hero shot, canonical Vercel first.

    Aliased ``*.vercel.app`` deployment URLs in auto_publish.json go stale;
    ``https://{product_id}.vercel.app`` is the stable production host.
    """
    pid = str(product_id or "").strip()
    urls: list[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        url = str(raw or "").strip()
        if not url.startswith("https://"):
            return
        key = url.rstrip("/")
        if key in seen:
            return
        seen.add(key)
        urls.append(url if url.endswith("/") else url + "/")

    if pid.startswith("prod-"):
        _add(f"https://{pid}.vercel.app/")
    try:
        from web.backend.services.product_catalog_publish import resolve_product_live_url

        _add(resolve_product_live_url(pid))
    except Exception:
        logger.debug("blog screenshot: live url resolve failed for %s", pid, exc_info=True)
    return urls


def page_answers(url: str, *, timeout: float = 15.0) -> bool:
    """True when the URL returns an HTTP answer (including 4xx). Transport failure is False."""
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": "aicom-blog-capture/1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(getattr(resp, "status", 0) or 0) > 0
    except urllib.error.HTTPError as exc:
        return int(getattr(exc, "code", 0) or 0) > 0
    except Exception:
        return False


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


def _screenshot_page(url: str, product_id: str) -> str | None:
    from playwright.sync_api import sync_playwright
    from PIL import Image

    out = blog_asset_path(product_id)
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
    logger.info("blog screenshot: saved %s for %s from %s", out.name, product_id, url)
    return blog_asset_public_url(product_id)


def capture_blog_hero(product_id: str, *, base_url: str | None = None) -> str | None:
    """Screenshot the live product (preferred) or sandbox landing. Returns public URL or None."""
    pid = str(product_id or "").strip()
    if not pid:
        return None

    for live in live_capture_page_urls(pid):
        if not page_answers(live):
            continue
        try:
            shot = _screenshot_page(live, pid)
            if shot:
                return shot
        except Exception:
            logger.warning("blog screenshot: live capture failed for %s (%s)", pid, live, exc_info=True)

    base = resolve_capture_base_url(base_url)
    index_rel = os.environ.get("BLOG_CAPTURE_INDEX_RELPATH", "index.html").strip().lstrip("/")
    try:
        data = _post_json(f"{base}/api/sandbox/start/{pid}")
        sandbox_id = str(data.get("sandbox_id") or "")
        if not sandbox_id.startswith("sandbox-"):
            logger.warning("blog screenshot: bad sandbox response for %s", pid)
        else:
            url = f"{base}/api/sandbox/file/{sandbox_id}/{index_rel}"
            shot = _screenshot_page(url, pid)
            if shot:
                return shot
    except Exception:
        logger.warning("blog screenshot: sandbox capture failed for %s", pid, exc_info=True)

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
