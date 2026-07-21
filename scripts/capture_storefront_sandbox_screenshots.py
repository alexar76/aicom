#!/usr/bin/env python3
"""
Capture sandbox previews for every product on the public storefront.

For each product:
  1. POST /api/sandbox/storefront/start/{product_id}
  2. Poll /api/sandbox/ready/{sandbox_id}
  3. Screenshot sandbox viewer + preview document

Output (default): ``test-screens/`` at repo root (gitignored).

Env:
  STOREFRONT_SCREEN_BASE_URL   default https://magic-ai-factory.com
  STOREFRONT_SCREEN_OUT_DIR    default <repo>/test-screens
  STOREFRONT_SCREEN_VIEWPORT   default 1440x900
  STOREFRONT_SCREEN_LIMIT      max products (default 100)
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "test-screens"


def _base_url() -> str:
    return os.environ.get("STOREFRONT_SCREEN_BASE_URL", "https://magic-ai-factory.com").rstrip("/")


def _out_dir() -> Path:
    raw = os.environ.get("STOREFRONT_SCREEN_OUT_DIR", "").strip()
    return Path(raw) if raw else DEFAULT_OUT


def _json_request(
    method: str,
    url: str,
    *,
    body: dict | None = None,
    timeout: float = 120.0,
) -> tuple[int, dict | list | str]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as e:
        status = e.code
        raw = e.read().decode("utf-8", errors="replace")
    try:
        return status, json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return status, raw


def _slug(pid: str, name: str) -> str:
    base = re.sub(r"[^\w.-]+", "-", (name or pid).strip().lower()).strip("-")[:48]
    return f"{pid}__{base}" if base else pid


def list_storefront_products(base: str, limit: int) -> list[dict]:
    status, payload = _json_request("GET", f"{base}/api/products?limit={limit}", timeout=60.0)
    if status != 200:
        raise SystemExit(f"GET /api/products failed HTTP {status}: {payload!r}")
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("products") or payload.get("items") or []
    else:
        items = []
    return [p for p in items if isinstance(p, dict) and p.get("id")]


def start_storefront_sandbox(base: str, product_id: str) -> tuple[int, dict]:
    return _json_request(
        "POST",
        f"{base}/api/sandbox/storefront/start/{product_id}",
        timeout=float(os.environ.get("STOREFRONT_SCREEN_START_TIMEOUT", "90")),
    )


def poll_ready(base: str, sandbox_id: str, *, max_wait: float = 45.0) -> dict:
    deadline = time.time() + max_wait
    last: dict = {}
    while time.time() < deadline:
        status, payload = _json_request("GET", f"{base}/api/sandbox/ready/{sandbox_id}", timeout=15.0)
        if status == 200 and isinstance(payload, dict):
            last = payload
            if payload.get("ready"):
                return payload
        time.sleep(0.6)
    return last


def main() -> int:
    base = _base_url()
    out_dir = _out_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        limit = int(os.environ.get("STOREFRONT_SCREEN_LIMIT", "100"))
    except ValueError:
        limit = 100

    vp = os.environ.get("STOREFRONT_SCREEN_VIEWPORT", "1440x900")
    w, h = (int(x) for x in vp.split("x", 1))

    products = list_storefront_products(base, limit)
    if not products:
        print("No storefront products returned.", file=sys.stderr)
        return 1

    manifest: list[dict] = []
    print(f"Base: {base}")
    print(f"Output: {out_dir}")
    print(f"Products: {len(products)}")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        context = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
        page = context.new_page()

        try:
            for i, product in enumerate(products, start=1):
                pid = str(product["id"])
                name = str(product.get("name") or product.get("title") or pid)
                slug = _slug(pid, name)
                row: dict = {
                    "product_id": pid,
                    "name": name,
                    "slug": slug,
                    "ok": False,
                }
                print(f"[{i}/{len(products)}] {pid} — {name}")

                status, start_payload = start_storefront_sandbox(base, pid)
                if status != 200 or not isinstance(start_payload, dict):
                    row["error"] = f"start HTTP {status}: {start_payload!r}"
                    (out_dir / f"{slug}.error.txt").write_text(row["error"], encoding="utf-8")
                    manifest.append(row)
                    print(f"  FAIL start: {row['error']}")
                    continue

                sandbox_id = str(start_payload.get("sandbox_id") or "")
                row["sandbox_id"] = sandbox_id
                row["compose_preview"] = (start_payload.get("compose_preview") or {}).get("status")
                row["preview_api"] = (start_payload.get("preview_api") or {}).get("status")

                ready = poll_ready(base, sandbox_id)
                row["ready"] = ready
                preview_path = "index.html"
                if isinstance(ready, dict) and ready.get("preview_path"):
                    preview_path = str(ready["preview_path"]).lstrip("/")

                view_url = f"{base}/api/sandbox/view/{sandbox_id}"
                file_url = f"{base}/api/sandbox/file/{sandbox_id}/{preview_path}"

                try:
                    page.goto(view_url, wait_until="networkidle", timeout=90_000)
                    page.wait_for_timeout(1500)
                    view_png = out_dir / f"{slug}__sandbox-view.png"
                    page.screenshot(path=str(view_png), full_page=True)
                    row["sandbox_view_png"] = view_png.name

                    page.goto(file_url, wait_until="load", timeout=90_000)
                    page.wait_for_timeout(1200)
                    preview_png = out_dir / f"{slug}__preview.png"
                    page.screenshot(path=str(preview_png), full_page=True)
                    row["preview_png"] = preview_png.name
                    row["ok"] = True
                    print(f"  OK → {view_png.name}, {preview_png.name}")
                except Exception as exc:
                    row["error"] = str(exc)
                    (out_dir / f"{slug}.error.txt").write_text(str(exc), encoding="utf-8")
                    print(f"  FAIL screenshot: {exc}")

                manifest.append(row)
                time.sleep(0.4)
        finally:
            page.close()
            context.close()
            browser.close()

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    ok_n = sum(1 for r in manifest if r.get("ok"))
    print(f"\nDone: {ok_n}/{len(manifest)} OK — manifest: {manifest_path}")
    return 0 if ok_n == len(manifest) else 2


if __name__ == "__main__":
    raise SystemExit(main())
