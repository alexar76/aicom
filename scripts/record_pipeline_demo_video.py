#!/usr/bin/env python3
"""
Record a Playwright video: Admin login → Live Monitor (wait for data) → Pipeline (wait for rows)
→ New Product → Pipeline until product id appears → wait until code exists → Sandbox → Start Sandbox → View popup.

Env:
  DEMO_VIDEO_BASE_URL       (default http://127.0.0.1:9080)
  ADMIN_PASSWORD
  DEMO_VIDEO_IDEA
  DEMO_VIDEO_PROFILE        set to full_software for SaaS/dashboard-focused default brief
  DEMO_VIDEO_OUT            output dir (default docs/gallery/recordings)
  DEMO_VIDEO_DWELL_MS       pause between steps (default 2200)
  DEMO_VIDEO_SANDBOX_WAIT_MS   max wait for /api/sandbox/products to list new pid (default 600000)
  DEMO_VIDEO_SKIP_SANDBOX_WAIT  set to 1 to skip waiting for code (sandbox section may be empty)
"""

from __future__ import annotations

import json
import os
import re
import time
import shutil
from pathlib import Path

BASE = os.environ.get("DEMO_VIDEO_BASE_URL", "http://127.0.0.1:9080").rstrip("/")
PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
_PROFILE = os.environ.get("DEMO_VIDEO_PROFILE", "").strip().lower()
_DEFAULT_FS = (
    "[VIDEO DEMO] SaaS for remote teams — JWT auth, dashboard with charts, tasks CRUD, "
    "SQLite or Postgres, settings page, OpenAPI."
)
_DEFAULT_LANDING = (
    "[VIDEO DEMO] Landing page for AI-powered resume builder — hero, features, pricing, waitlist."
)
if os.environ.get("DEMO_VIDEO_IDEA"):
    IDEA = os.environ["DEMO_VIDEO_IDEA"]
elif _PROFILE == "full_software":
    IDEA = _DEFAULT_FS
else:
    IDEA = _DEFAULT_LANDING
REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("DEMO_VIDEO_OUT", str(REPO_ROOT / "docs/gallery/recordings")))
DWELL_MS = int(os.environ.get("DEMO_VIDEO_DWELL_MS", "2200"))
SANDBOX_WAIT_MS = int(os.environ.get("DEMO_VIDEO_SANDBOX_WAIT_MS", "600000"))
SKIP_SANDBOX_WAIT = os.environ.get("DEMO_VIDEO_SKIP_SANDBOX_WAIT", "").strip().lower() in (
    "1",
    "true",
    "yes",
)


def _sleep(page, ms: int | None = None) -> None:
    page.wait_for_timeout(ms if ms is not None else DWELL_MS)


def _nav_tab(page, idx: int) -> None:
    page.locator("aside nav").first.locator("button").nth(idx).click(timeout=25_000)
    _sleep(page, max(900, DWELL_MS // 2))


def _wait_monitor_ready(page) -> None:
    hint = page.get_by_text("Connecting to metrics stream...")
    try:
        hint.wait_for(state="hidden", timeout=120_000)
    except Exception:
        page.wait_for_load_state("networkidle", timeout=60_000)
    _sleep(page, max(1500, DWELL_MS))


def _wait_pipeline_ready(page) -> None:
    page.get_by_text("Loading pipeline data...").wait_for(state="hidden", timeout=120_000)
    page.wait_for_function(
        """() => {
          const t = document.body.innerText || '';
          if (t.includes('No active products in the pipeline')) return true;
          if (/prod-[a-z0-9]{8,24}/i.test(t)) return true;
          if (/IDEA_RECEIVED|SPEC_WRITTEN|CODE_COMMITTED|COMPLETED|QA_/i.test(t)) return true;
          return false;
        }""",
        timeout=30_000,
    )
    _sleep(page, max(2000, int(DWELL_MS * 1.2)))


def _submit_new_product(page, idea: str) -> str:
    """POST /api/admin/products/create — UI banner is async; response is authoritative."""

    def _is_create(resp) -> bool:
        try:
            return "/api/admin/products/create" in resp.url and resp.request.method == "POST"
        except Exception:
            return False

    last_err: str | None = None
    for attempt in range(6):
        page.get_by_placeholder("Describe the product you want to build...").fill(idea)
        _sleep(page, 700)
        with page.expect_response(_is_create, timeout=120_000) as nav:
            page.get_by_role("button", name="Start Building").click(timeout=60_000)
        resp = nav.value
        body = {}
        try:
            body = resp.json()
        except Exception:
            pass
        if resp.status >= 400:
            last_err = f"HTTP {resp.status}: {body or (resp.text() or '')[:400]}"
            _sleep(page, 2500)
            continue
        pid = body.get("product_id")
        if not pid:
            last_err = f"no product_id: {body}"
            _sleep(page, 2500)
            continue
        try:
            page.wait_for_selector("text=Product created successfully!", timeout=30_000)
        except Exception:
            pass
        return str(pid)
    raise RuntimeError(f"create product failed after retries: {last_err}")


def _wait_pid_on_pipeline_tab(page, pid: str) -> None:
    _nav_tab(page, 2)
    page.get_by_text("Loading pipeline data...").wait_for(state="hidden", timeout=120_000)
    loc = page.get_by_text(pid, exact=False).first
    loc.wait_for(state="visible", timeout=180_000)
    _sleep(page, max(2500, DWELL_MS))


def _ensure_sandbox_ui_row(page, pid: str, timeout_ms: int = 240_000) -> None:
    """SandboxTab keeps cached state; poll Refresh until the gray subtitle row exists."""
    pat = re.compile(rf"{re.escape(pid)}\s*·\s*")
    loc = page.locator("p.text-xs.text-gray-500").filter(has_text=pat)
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        try:
            if loc.count() > 0:
                loc.first.scroll_into_view_if_needed(timeout=45_000)
                loc.first.wait_for(state="visible", timeout=45_000)
                return
        except Exception:
            pass
        try:
            page.get_by_role("button", name=re.compile(r"refresh", re.I)).first.click(timeout=12_000)
        except Exception:
            pass
        page.wait_for_timeout(2200)
    raise TimeoutError(f"Sandbox UI never showed code row for {pid}")


def _wait_sandbox_api_has_pid(page, pid: str) -> None:
    if SKIP_SANDBOX_WAIT:
        print("[video] DEMO_VIDEO_SKIP_SANDBOX_WAIT=1 — not waiting for generated code.", flush=True)
        return
    pj = json.dumps(pid)
    deadline = time.monotonic() + SANDBOX_WAIT_MS / 1000
    streak = 0
    while time.monotonic() < deadline:
        ok = page.evaluate(
            f"""async () => {{
          const productId = {pj};
          const r = await fetch('/api/sandbox/products', {{
            credentials: 'same-origin',
            cache: 'no-store',
          }});
          if (!r.ok) return false;
          const j = await r.json();
          const arr = j.products || [];
          return Array.isArray(arr) &&
            arr.some((p) => p && p.product_id === productId && p.sandbox_ready === true);
        }}"""
        )
        streak = streak + 1 if ok else 0
        if streak >= 2:
            return
        page.wait_for_timeout(900)
    raise TimeoutError(f"sandbox_ready not stable for {pid} within {SANDBOX_WAIT_MS}ms")


def main() -> Path | None:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    before = {p for p in OUT.glob("*.webm")}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        context = browser.new_context(
            record_video_dir=str(OUT),
            record_video_size={"width": 1280, "height": 720},
            viewport={"width": 1280, "height": 720},
        )
        page = context.new_page()
        pid_holder: dict[str, str] = {}

        try:
            page.goto(f"{BASE}/admin/login", wait_until="domcontentloaded", timeout=90_000)
            _sleep(page, 1200)
            pass_input = page.get_by_placeholder("Enter admin password").or_(
                page.locator("input[type='password']")
            )
            pass_input.first.fill(PASSWORD)
            page.get_by_role("button", name=re.compile(r"^login$", re.I)).click()
            page.wait_for_url("**/admin**", timeout=60_000)
            _sleep(page, 1500)

            _nav_tab(page, 1)
            _wait_monitor_ready(page)
            _sleep(page, max(3000, DWELL_MS))

            _nav_tab(page, 2)
            _wait_pipeline_ready(page)

            _nav_tab(page, 3)
            _sleep(page, 800)
            pid = _submit_new_product(page, IDEA)
            pid_holder["pid"] = pid
            print(f"[video] Created product {pid}", flush=True)
            _sleep(page, max(3500, DWELL_MS))

            _wait_pid_on_pipeline_tab(page, pid)
            page.mouse.wheel(0, 420)
            _sleep(page, max(3000, DWELL_MS))

            try:
                _wait_sandbox_api_has_pid(page, pid)
                print(f"[video] Sandbox API lists {pid} — opening Sandbox tab", flush=True)
            except Exception as e:
                print(f"[video] Timeout waiting for generated code ({e}); continuing to Sandbox tab anyway.", flush=True)

            try:
                _nav_tab(page, 10)
                _sleep(page, max(2000, DWELL_MS))
                page.get_by_role("button", name=re.compile(r"refresh", re.I)).first.click(timeout=15_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=45_000)
                except Exception:
                    pass
                _sleep(page, max(3500, DWELL_MS))

                _ensure_sandbox_ui_row(page, pid, timeout_ms=240_000)

                # Subtitle is gray path line under title; list can be long — scroll into view first.
                sub = page.locator("p.text-xs.text-gray-500").filter(
                    has_text=re.compile(rf"{re.escape(pid)}\s*·\s*")
                )
                sub.scroll_into_view_if_needed(timeout=120_000)
                sub.wait_for(state="visible", timeout=120_000)
                # GlassCard also uses cursor-pointer — target the product row header (flex + justify-between).
                sub.locator(
                    "xpath=ancestor::div[contains(@class,'justify-between') "
                    "and contains(@class,'cursor-pointer')][1]"
                ).click(timeout=60_000)
                _sleep(page, 1200)
                card_root = sub.locator("xpath=ancestor::div[contains(@class,'overflow-hidden')][1]")
                sb_btn = card_root.get_by_role("button", name="Start Sandbox")
                sb_btn.wait_for(state="visible", timeout=60_000)
                sb_btn.click(timeout=60_000)
                _sleep(page, max(4000, DWELL_MS))

                # "View" opens the iframe preview — lives in Active Sandboxes (not the expanded code card).
                view_btn = (
                    page.locator("div.bg-white\\/5.rounded-xl")
                    .filter(has_text=re.escape(pid))
                    .get_by_role("button", name=re.compile(r"^View$"))
                )
                try:
                    with page.expect_popup(timeout=45_000) as pop:
                        view_btn.click(timeout=20_000)
                    sp = pop.value
                    sp.wait_for_load_state("domcontentloaded", timeout=45_000)
                    _sleep(sp, max(5000, DWELL_MS * 2))
                    sp.close()
                except Exception as ve:
                    print(f"[video] View popup: {ve}", flush=True)
            except Exception as sb_exc:
                print(f"[video] Sandbox tab flow skipped: {sb_exc}", flush=True)

            _nav_tab(page, 2)
            page.get_by_text("Loading pipeline data...").wait_for(state="hidden", timeout=120_000)
            try:
                page.get_by_text(pid, exact=False).first.scroll_into_view_if_needed(timeout=15_000)
            except Exception:
                pass
            _sleep(page, max(4000, DWELL_MS * 1.5))

        finally:
            page.close()
            context.close()
            browser.close()

    after = {p for p in OUT.glob("*.webm")}
    new_files = sorted(after - before, key=lambda x: x.stat().st_mtime)
    if not new_files:
        print("No .webm produced.", flush=True)
        return None
    latest = new_files[-1]
    dest = OUT / "pipeline-demo-latest.webm"
    shutil.copy2(latest, dest)
    print(f"OK — {latest}", flush=True)
    print(f"    → {dest}", flush=True)
    return dest


if __name__ == "__main__":
    main()
