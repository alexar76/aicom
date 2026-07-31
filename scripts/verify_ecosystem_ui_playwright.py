#!/usr/bin/env python3
"""Headless Playwright smoke for deployed ecosystem UIs (Factory, Monitor, Pulse)."""
from __future__ import annotations

import os
import sys
import time


def _check(name: str, ok: bool, detail: str = "") -> bool:
    tag = "PASS" if ok else "FAIL"
    extra = f" — {detail}" if detail else ""
    print(f"[{tag}] {name}{extra}")
    return ok


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("FAIL: playwright not installed", file=sys.stderr)
        return 2

    factory = os.environ.get("ECOSYSTEM_UI_FACTORY_URL", "http://127.0.0.1:9080").rstrip("/")
    # Built with VITE_BASE_PATH=/monitor/ — assets resolve via nginx /monitor/ (not bare :9100).
    monitor = os.environ.get(
        "ECOSYSTEM_UI_MONITOR_URL",
        "https://magic-ai-factory.com/monitor/",
    ).rstrip("/") + "/"
    pulse = os.environ.get("ECOSYSTEM_UI_PULSE_URL", "http://127.0.0.1:5199/pulse/").rstrip("/") + "/"
    wait_s = float(os.environ.get("ECOSYSTEM_UI_WAIT_S", "14"))

    ok_all = True
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--use-gl=swiftshader"],
        )
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        # Factory storefront
        try:
            page.goto(factory, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_load_state("networkidle", timeout=20000)
            body_len = len((page.locator("body").inner_text(timeout=5000) or ""))
            ok_all &= _check(
                "Factory storefront renders",
                body_len > 80,
                f"body_chars={body_len}",
            )
        except Exception as exc:
            ok_all &= _check("Factory storefront renders", False, str(exc))

        # Factory admin login (SSR + client hydration)
        try:
            page.goto(f"{factory}/admin/login", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_selector('input[type="password"]', timeout=15000)
            has_login = page.locator('input[type="password"]').count() > 0
            ok_all &= _check("Factory admin login UI", has_login)
        except Exception as exc:
            ok_all &= _check("Factory admin login UI", False, str(exc))

        # Alien Monitor (WebGL canvas)
        try:
            page.goto(monitor, wait_until="domcontentloaded", timeout=45000)
            time.sleep(wait_s)
            for _ in range(30):
                if page.locator("canvas").count() > 0:
                    break
                time.sleep(0.5)
            canvas = page.locator("canvas")
            ok_all &= _check(
                "Monitor 3D canvas present",
                canvas.count() > 0,
                f"canvases={canvas.count()}",
            )
            health = page.evaluate(
                """async () => {
                  try {
                    const r = await fetch('api/health');
                    const j = await r.json();
                    return j.status === 'ok';
                  } catch { return false; }
                }"""
            )
            ok_all &= _check("Monitor API health via browser", bool(health))
        except Exception as exc:
            ok_all &= _check("Monitor 3D canvas present", False, str(exc))

        # Pulse Terminal
        try:
            page.goto(pulse, wait_until="domcontentloaded", timeout=45000)
            time.sleep(5)
            title = page.title() or ""
            root = page.locator("#root, main, body")
            text = (root.first.inner_text(timeout=8000) if root.count() else "") or ""
            if len(text.strip()) < 20 and "Pulse" in title:
                text = title
            ok_all &= _check(
                "Pulse Terminal UI",
                len(text.strip()) > 20,
                f"chars={len(text)}",
            )
        except Exception as exc:
            ok_all &= _check("Pulse Terminal UI", False, str(exc))

        browser.close()

    print("")
    print("ECOSYSTEM UI SMOKE:", "PASS" if ok_all else "FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
