#!/usr/bin/env python3
"""
Record a Playwright admin walkthrough video for README / marketing hero.

Modes (``DEMO_VIDEO_MODE``):
  admin     — **Admin demo replay:** Dashboard + Pipeline only (deep scroll) — default
              for ``pipeline-demo-latest.webm`` / Live Monitor.
  tour      — long UI tour: all admin tabs + sandbox + public homepage.
  pipeline  — legacy: enqueue one product + wait for sandbox preview.
  full      — tour first, then optional shortened pipeline tail (no long codegen wait).

Env:
  DEMO_VIDEO_BASE_URL          default http://127.0.0.1:9080
  ADMIN_PASSWORD               required
  ADMIN_USERNAME               default admin
  DEMO_VIDEO_MODE              admin | tour | pipeline | full
  DEMO_VIDEO_OUT               default docs/gallery/recordings
  DEMO_VIDEO_DWELL_MS          pause between steps (default 1800)
  DEMO_VIDEO_SCROLL_MS         pause per scroll step (default 650)
  DEMO_VIDEO_SCROLL_STEPS      scroll ticks per section (default 8)
  DEMO_VIDEO_VIEWPORT_W/H      default 1440 / 900
  DEMO_VIDEO_SANDBOX_PRODUCT_ID  override preview product (default prod-demo-landing-waitlist)
  DEMO_VIDEO_SKIP_SANDBOX      set 1 to skip sandbox popup in tour
  DEMO_VIDEO_IDEA / DEMO_VIDEO_PROFILE — pipeline & full modes only
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

BASE = os.environ.get("DEMO_VIDEO_BASE_URL", "http://127.0.0.1:9080").rstrip("/")
PASSWORD = os.environ.get("ADMIN_PASSWORD", "").strip()
ADMIN_USER = os.environ.get("ADMIN_USERNAME", "admin").strip() or "admin"
if not PASSWORD:
    raise SystemExit("Set ADMIN_PASSWORD (bootstrap admin password)")

MODE = os.environ.get("DEMO_VIDEO_MODE", "admin").strip().lower()
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
DWELL_MS = int(os.environ.get("DEMO_VIDEO_DWELL_MS", "1800"))
SCROLL_MS = int(os.environ.get("DEMO_VIDEO_SCROLL_MS", "650"))
SCROLL_STEPS = int(os.environ.get("DEMO_VIDEO_SCROLL_STEPS", "8"))
VIEW_W = int(os.environ.get("DEMO_VIDEO_VIEWPORT_W", "1440"))
VIEW_H = int(os.environ.get("DEMO_VIDEO_VIEWPORT_H", "900"))
SANDBOX_PID = os.environ.get("DEMO_VIDEO_SANDBOX_PRODUCT_ID", "prod-demo-landing-waitlist").strip()
SKIP_SANDBOX = os.environ.get("DEMO_VIDEO_SKIP_SANDBOX", "").strip().lower() in ("1", "true", "yes")
SANDBOX_WAIT_MS = int(os.environ.get("DEMO_VIDEO_SANDBOX_WAIT_MS", "600000"))
SKIP_SANDBOX_WAIT = os.environ.get("DEMO_VIDEO_SKIP_SANDBOX_WAIT", "").strip().lower() in (
    "1",
    "true",
    "yes",
)


def _sleep(page, ms: int | None = None) -> None:
    page.wait_for_timeout(ms if ms is not None else DWELL_MS)


def _main_locator(page):
    return page.locator("main").first


def _scroll_main(page, steps: int | None = None, delta: int = 520) -> None:
    steps = SCROLL_STEPS if steps is None else steps
    main = _main_locator(page)
    for _ in range(steps):
        main.evaluate("(el, d) => el.scrollBy({ top: d, behavior: 'smooth' })", delta)
        _sleep(page, SCROLL_MS)
    _sleep(page, max(1200, DWELL_MS // 2))


def _scroll_main_to_top(page) -> None:
    _main_locator(page).evaluate("(el) => el.scrollTo({ top: 0, behavior: 'instant' })")
    _sleep(page, 500)


def _goto_tab(page, tab: str) -> None:
    page.goto(f"{BASE}/admin?tab={tab}", wait_until="domcontentloaded", timeout=90_000)
    try:
        page.wait_for_load_state("networkidle", timeout=25_000)
    except Exception:
        pass
    _sleep(page, max(1400, DWELL_MS))


def _expand_sidebar(page) -> None:
    """Desktop sidebar starts collapsed — expand so nav labels are visible on video."""
    try:
        chevron = page.locator("aside button.hidden.md\\:flex").first
        if chevron.is_visible(timeout=3_000):
            chevron.click(timeout=8_000)
            _sleep(page, 900)
    except Exception:
        pass


def _dismiss_overlays(page) -> None:
    for label in (
        "Dismiss",
        "Got it",
        "Skip",
        "Close",
        "Not now",
    ):
        try:
            page.get_by_role("button", name=re.compile(rf"^{label}$", re.I)).first.click(
                timeout=2_500
            )
            _sleep(page, 500)
        except Exception:
            pass
    try:
        page.locator("button[title='Dismiss']").first.click(timeout=2_000)
    except Exception:
        pass
    try:
        page.get_by_label(re.compile(r"dismiss", re.I)).first.click(timeout=2_000)
    except Exception:
        pass


def _login(page) -> None:
    """API login + token in localStorage (reliable for production)."""
    resp = page.request.post(
        f"{BASE}/api/admin/auth/login",
        data=json.dumps({"username": ADMIN_USER, "password": PASSWORD}),
        headers={"Content-Type": "application/json"},
    )
    if not resp.ok:
        raise RuntimeError(f"Admin login failed: HTTP {resp.status} {resp.text()[:200]}")
    token = resp.json().get("access_token")
    if not token:
        raise RuntimeError("Admin login: no access_token")
    page.goto(f"{BASE}/admin/login", wait_until="domcontentloaded", timeout=90_000)
    page.evaluate(
        "(t) => { localStorage.setItem('admin_token', t); }",
        token,
    )
    page.goto(f"{BASE}/admin?tab=dashboard", wait_until="domcontentloaded", timeout=90_000)
    _sleep(page, 1500)
    _expand_sidebar(page)
    _dismiss_overlays(page)


def _wait_monitor_ready(page) -> None:
    try:
        page.get_by_text("Connecting to metrics stream...").wait_for(state="hidden", timeout=120_000)
    except Exception:
        page.wait_for_load_state("networkidle", timeout=60_000)
    _sleep(page, max(2000, DWELL_MS))


def _wait_pipeline_ready(page) -> None:
    try:
        page.get_by_text("Loading pipeline data...").wait_for(state="hidden", timeout=120_000)
    except Exception:
        pass
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            body = _main_text(page)
        except Exception:
            page.wait_for_timeout(800)
            continue
        if "No active products in the pipeline" in body or re.search(
            r"prod-[a-z0-9]{8,24}", body, re.I
        ):
            break
        page.wait_for_timeout(800)
    _sleep(page, max(1800, DWELL_MS))


def _main_text(page) -> str:
    try:
        return page.locator("main").first.inner_text(timeout=8_000)
    except Exception:
        return page.locator("body").inner_text(timeout=8_000)


def _wait_dashboard_ready(page) -> None:
    """Wait until KPI cards show real counts (not all zeros / loading)."""
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            ok = page.evaluate(
                """async () => {
                  const token = localStorage.getItem('admin_token');
                  if (!token) return false;
                  const r = await fetch('/api/admin/dashboard?quick=true', {
                    headers: { Authorization: 'Bearer ' + token },
                    cache: 'no-store',
                  });
                  if (!r.ok) return false;
                  const d = await r.json();
                  const p = d.pipeline || {};
                  const total = Number(p.total_products) || 0;
                  const active = Number(p.active_products) || 0;
                  const completed = Number(p.completed_products) || 0;
                  return total > 0 || active > 0 || completed > 0;
                }"""
            )
            if ok:
                print("[video] Dashboard metrics loaded (non-zero)", flush=True)
                break
        except Exception:
            pass
        page.wait_for_timeout(1200)
    else:
        print("[video] WARNING: dashboard metrics still zero — recording anyway", flush=True)
    _sleep(page, max(2500, DWELL_MS))


def _tour_dashboard(page, *, deep: bool = False) -> None:
    print("[video] Dashboard", flush=True)
    _goto_tab(page, "dashboard")
    _wait_dashboard_ready(page)
    _scroll_main_to_top(page)
    _sleep(page, max(3000, DWELL_MS))
    steps = SCROLL_STEPS + (12 if deep else 2)
    _scroll_main(page, steps=steps, delta=460)
    _scroll_main_to_top(page)
    _sleep(page, max(2800, DWELL_MS))
    if deep:
        _scroll_main(page, steps=8, delta=420)
        _sleep(page, max(3500, DWELL_MS))


def _tour_monitor(page) -> None:
    print("[video] Live Monitor", flush=True)
    _goto_tab(page, "monitor")
    _wait_monitor_ready(page)
    _scroll_main_to_top(page)
    _sleep(page, max(2800, DWELL_MS))
    _scroll_main(page, steps=SCROLL_STEPS + 4, delta=440)
    try:
        page.locator("video").first.scroll_into_view_if_needed(timeout=12_000)
        _sleep(page, max(3500, DWELL_MS * 1.5))
    except Exception:
        pass
    _scroll_main(page, steps=5, delta=500)


def _tour_pipeline(page, *, deep: bool = False) -> None:
    print("[video] Pipeline", flush=True)
    _goto_tab(page, "pipeline")
    _wait_pipeline_ready(page)
    _scroll_main_to_top(page)
    _sleep(page, max(2800, DWELL_MS))
    _scroll_main(page, steps=SCROLL_STEPS + (14 if deep else 6), delta=520)
    hints = ("prod-demo", "COMPLETED", "HUMAN_REVIEW", "DEV_FIXING", "QA_", "CODE_")
    expanded = 0
    max_expand = 3 if deep else 1
    for pid_hint in hints:
        if expanded >= max_expand:
            break
        try:
            row = page.get_by_text(re.compile(pid_hint, re.I)).first
            row.scroll_into_view_if_needed(timeout=12_000)
            row.click(timeout=10_000)
            _sleep(page, max(3200, DWELL_MS))
            _scroll_main(page, steps=5 if deep else 4, delta=420)
            expanded += 1
        except Exception:
            continue
    _scroll_main(page, steps=10 if deep else 6, delta=540)
    if deep:
        _scroll_main_to_top(page)
        _sleep(page, max(2500, DWELL_MS))


def _tour_director(page) -> None:
    print("[video] Director", flush=True)
    _goto_tab(page, "director")
    _scroll_main_to_top(page)
    _sleep(page, max(2200, DWELL_MS))
    _scroll_main(page, steps=SCROLL_STEPS + 3, delta=500)


def _tour_discovery(page) -> None:
    print("[video] Discovery", flush=True)
    _goto_tab(page, "discovery")
    _scroll_main_to_top(page)
    _sleep(page, max(2000, DWELL_MS))
    _scroll_main(page, steps=SCROLL_STEPS + 2, delta=480)


def _tour_providers(page) -> None:
    print("[video] LLM Providers", flush=True)
    _goto_tab(page, "providers")
    _scroll_main_to_top(page)
    _sleep(page, max(2200, DWELL_MS))
    _scroll_main(page, steps=SCROLL_STEPS + 2, delta=460)
    try:
        page.get_by_text(re.compile(r"circuit|breaker|provider", re.I)).first.scroll_into_view_if_needed(
            timeout=10_000
        )
        _sleep(page, max(2500, DWELL_MS))
    except Exception:
        pass
    _scroll_main(page, steps=4, delta=420)


def _tour_llm_logs(page) -> None:
    print("[video] LLM Logs", flush=True)
    _goto_tab(page, "llm-logs")
    _scroll_main_to_top(page)
    _sleep(page, max(1800, DWELL_MS))
    _scroll_main(page, steps=SCROLL_STEPS, delta=500)


def _tour_agents(page) -> None:
    print("[video] Agents", flush=True)
    _goto_tab(page, "agents")
    _scroll_main_to_top(page)
    _sleep(page, max(2000, DWELL_MS))
    _scroll_main(page, steps=SCROLL_STEPS, delta=480)


def _tour_workshop(page) -> None:
    print("[video] Workshop", flush=True)
    _goto_tab(page, "workshop")
    _scroll_main_to_top(page)
    _sleep(page, max(2000, DWELL_MS))
    _scroll_main(page, steps=SCROLL_STEPS, delta=450)


def _api_start_sandbox(page, pid: str) -> str | None:
    """Start sandbox via API; return sandbox_id when present."""
    try:
        res = page.request.post(
            f"{BASE}/api/sandbox/start/{pid}",
            headers={"Content-Type": "application/json"},
            timeout=120_000,
        )
        if not res.ok:
            print(f"[video] API sandbox/start {pid} → HTTP {res.status}", flush=True)
            return None
        body = res.json()
        sid = body.get("sandbox_id") or body.get("id")
        print(f"[video] API sandbox/start {pid} → {sid or 'ok'}", flush=True)
        _sleep(page, max(5000, DWELL_MS * 2))
        return str(sid) if sid else None
    except Exception as exc:
        print(f"[video] API sandbox/start failed: {exc}", flush=True)
        return None


def _tour_sandbox_preview(page, pid: str) -> None:
    if SKIP_SANDBOX:
        return
    print(f"[video] Sandbox preview ({pid})", flush=True)
    sandbox_id = _api_start_sandbox(page, pid)
    _goto_tab(page, "sandbox")
    _sleep(page, max(2000, DWELL_MS))
    _scroll_main_to_top(page)
    _scroll_main(page, steps=5, delta=450)
    try:
        page.get_by_role("button", name=re.compile(r"refresh", re.I)).first.click(timeout=12_000)
        _sleep(page, 2000)
    except Exception:
        pass
    pat = re.compile(rf"{re.escape(pid)}")
    try:
        sub = page.locator("p.text-xs.text-gray-500").filter(has_text=pat).first
        sub.scroll_into_view_if_needed(timeout=60_000)
        sub.wait_for(state="visible", timeout=60_000)
        sub.locator(
            "xpath=ancestor::div[contains(@class,'justify-between') "
            "and contains(@class,'cursor-pointer')][1]"
        ).click(timeout=30_000)
    except Exception:
        try:
            page.get_by_text(pid, exact=False).first.click(timeout=20_000)
        except Exception:
            print(f"[video] Could not expand sandbox row for {pid}", flush=True)
    _sleep(page, 1200)
    try:
        card = page.locator("p.text-xs.text-gray-500").filter(has_text=pat).locator(
            "xpath=ancestor::div[contains(@class,'overflow-hidden')][1]"
        )
        sb_btn = card.get_by_role("button", name=re.compile(r"Start Sandbox", re.I))
        if sb_btn.is_visible(timeout=5_000):
            sb_btn.click(timeout=30_000)
            _sleep(page, max(4500, DWELL_MS * 2))
    except Exception:
        pass
    preview_opened = False
    if sandbox_id:
        try:
            view_url = f"{BASE}/api/sandbox/view/{sandbox_id}"
            sp = page.context.new_page()
            sp.goto(view_url, wait_until="domcontentloaded", timeout=90_000)
            _sleep(sp, max(6000, DWELL_MS * 2))
            sp.mouse.wheel(0, 700)
            _sleep(sp, max(3500, DWELL_MS))
            sp.mouse.wheel(0, 900)
            _sleep(sp, max(4500, DWELL_MS))
            sp.close()
            preview_opened = True
        except Exception as exc:
            print(f"[video] Direct sandbox view: {exc}", flush=True)
    if not preview_opened:
        try:
            view_btn = (
                page.locator("div")
                .filter(has_text=re.compile(re.escape(pid)))
                .get_by_role("button", name=re.compile(r"^View$", re.I))
                .first
            )
            with page.expect_popup(timeout=45_000) as pop:
                view_btn.click(timeout=25_000)
            sp = pop.value
            sp.wait_for_load_state("domcontentloaded", timeout=45_000)
            _sleep(sp, max(6000, DWELL_MS * 2))
            sp.mouse.wheel(0, 600)
            _sleep(sp, max(3500, DWELL_MS))
            sp.mouse.wheel(0, 800)
            _sleep(sp, max(4000, DWELL_MS))
            sp.close()
        except Exception as exc:
            print(f"[video] Sandbox View popup: {exc}", flush=True)


def _tour_public_home(page) -> None:
    print("[video] Public homepage", flush=True)
    page.goto(f"{BASE}/", wait_until="domcontentloaded", timeout=90_000)
    _sleep(page, max(3000, DWELL_MS * 1.5))
    page.mouse.wheel(0, 500)
    _sleep(page, max(2200, DWELL_MS))
    page.mouse.wheel(0, 700)
    _sleep(page, max(2800, DWELL_MS))
    try:
        page.locator("video").first.scroll_into_view_if_needed(timeout=8_000)
        _sleep(page, max(3500, DWELL_MS))
    except Exception:
        pass
    page.mouse.wheel(0, 400)
    _sleep(page, max(2000, DWELL_MS))


def _run_admin_core_tour(page) -> None:
    """Demo replay focus: operator Dashboard + Pipeline monitor."""
    _tour_dashboard(page, deep=True)
    _tour_pipeline(page, deep=True)
    _goto_tab(page, "dashboard")
    _scroll_main_to_top(page)
    _sleep(page, max(2500, DWELL_MS))


def _run_admin_tour(page) -> None:
    _tour_dashboard(page)
    _tour_monitor(page)
    _tour_pipeline(page)
    _tour_director(page)
    _tour_discovery(page)
    _tour_providers(page)
    _tour_llm_logs(page)
    _tour_agents(page)
    _tour_workshop(page)
    _tour_sandbox_preview(page, SANDBOX_PID)
    _tour_public_home(page)


def _submit_new_product(page, idea: str) -> str:
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
            page.get_by_role("button", name=re.compile(r"Start Building", re.I)).click(timeout=60_000)
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
        return str(pid)
    raise RuntimeError(f"create product failed after retries: {last_err}")


def _wait_sandbox_api_has_pid(page, pid: str) -> None:
    if SKIP_SANDBOX_WAIT:
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


def _run_pipeline_tail(page) -> None:
    print("[video] Pipeline tail — new product", flush=True)
    _goto_tab(page, "new-product")
    _sleep(page, 800)
    pid = _submit_new_product(page, IDEA)
    print(f"[video] Created {pid}", flush=True)
    _goto_tab(page, "pipeline")
    _wait_pipeline_ready(page)
    try:
        page.get_by_text(pid, exact=False).first.scroll_into_view_if_needed(timeout=30_000)
    except Exception:
        pass
    _scroll_main(page, steps=5, delta=450)
    try:
        _wait_sandbox_api_has_pid(page, pid)
    except Exception as exc:
        print(f"[video] sandbox wait skipped: {exc}", flush=True)
    _tour_sandbox_preview(page, pid)


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
            record_video_size={"width": VIEW_W, "height": VIEW_H},
            viewport={"width": VIEW_W, "height": VIEW_H},
        )
        page = context.new_page()
        try:
            _login(page)
            if MODE == "admin":
                _run_admin_core_tour(page)
            elif MODE == "pipeline":
                _run_pipeline_tail(page)
            elif MODE == "full":
                _run_admin_tour(page)
                _run_pipeline_tail(page)
            elif MODE == "tour":
                _run_admin_tour(page)
            else:
                raise SystemExit(f"Unknown DEMO_VIDEO_MODE={MODE!r}")
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
    gen = REPO_ROOT / "scripts" / "generate_readme_hero_assets.py"
    if gen.is_file():
        print("Generating README GIF + MP4 + public/demo copies…", flush=True)
        subprocess.run([sys.executable, str(gen)], check=False)
    return dest


if __name__ == "__main__":
    main()
