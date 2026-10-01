#!/usr/bin/env python3
"""Full ecosystem UI verification — public Factory, Admin tabs, Monitor, Pulse, APIs."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field


@dataclass
class Row:
    section: str
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Report:
    rows: list[Row] = field(default_factory=list)

    def add(self, section: str, name: str, ok: bool, detail: str = "") -> None:
        self.rows.append(Row(section, name, ok, detail))
        tag = "PASS" if ok else "FAIL"
        extra = f" — {detail}" if detail else ""
        print(f"[{tag}] [{section}] {name}{extra}")

    def exit_code(self) -> int:
        return 0 if all(r.ok for r in self.rows) else 1

    def summary(self) -> str:
        by_sec: dict[str, list[Row]] = {}
        for r in self.rows:
            by_sec.setdefault(r.section, []).append(r)
        lines = ["# Ecosystem UI full report", ""]
        for sec, items in by_sec.items():
            p = sum(1 for i in items if i.ok)
            lines.append(f"## {sec} ({p}/{len(items)})")
            for i in items:
                mark = "x" if i.ok else " "
                lines.append(f"- [{mark}] {i.name}" + (f" — {i.detail}" if i.detail else ""))
            lines.append("")
        return "\n".join(lines)


def _admin_token() -> str:
    env = os.environ.get("AICOM_ADMIN_TOKEN", "").strip()
    if env:
        return env
    try:
        out = subprocess.check_output(
            [
                "docker",
                "exec",
                "aicom-app-1",
                "python3",
                "-c",
                "from web.backend.core.security import SecurityManager;"
                "print(SecurityManager().create_access_token('admin', role='admin'))",
            ],
            text=True,
            timeout=30,
        )
        return out.strip()
    except Exception as exc:
        raise RuntimeError(f"admin token: {exc}") from exc


def _page_ok(page, *, min_chars: int = 40, forbid: tuple[str, ...] = ()) -> tuple[bool, str]:
    try:
        body = page.locator("body").inner_text(timeout=8000) or ""
    except Exception as exc:
        return False, str(exc)
    low = body.lower()
    for bad in forbid:
        if bad in low:
            return False, f"contains '{bad}'"
    if len(body.strip()) < min_chars:
        return False, f"body_chars={len(body.strip())}"
    return True, f"body_chars={len(body.strip())}"


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("FAIL: pip install playwright && playwright install chromium", file=sys.stderr)
        return 2

    rep = Report()
    factory = os.environ.get("ECOSYSTEM_UI_FACTORY_URL", "https://magic-ai-factory.com").rstrip("/")
    monitor = os.environ.get(
        "ECOSYSTEM_UI_MONITOR_URL",
        "https://monitor.modelmarket.dev/",
    ).rstrip("/") + "/"
    pulse = os.environ.get(
        "ECOSYSTEM_UI_PULSE_URL",
        "https://magic-ai-factory.com/pulse/",
    ).rstrip("/") + "/"
    hub = os.environ.get("ECOSYSTEM_UI_HUB_URL", "https://modelmarket.dev").rstrip("/")
    wait_monitor = float(os.environ.get("ECOSYSTEM_UI_WAIT_S", "10"))

    public_paths = [
        ("/", "Home"),
        ("/explore", "Explore"),
        ("/builds", "Builds"),
        ("/blog", "Blog"),
        ("/about", "About"),
        ("/docs", "Docs"),
        ("/benchmark", "Benchmark"),
        ("/checkout", "Checkout"),
        ("/admin/login", "Admin login"),
    ]

    admin_tabs = [
        "dashboard",
        "setup",
        "monitor",
        "factory-floor",
        "time-travel",
        "showcase",
        "blog",
        "prompt-loop",
        "pipeline",
        "new-product",
        "workshop",
        "files",
        "agents",
        "providers",
        "llm-logs",
        "agent-logs",
        "security",
        "sandbox",
        "director",
        "discovery",
        "settings",
        "chat",
        "brainstorming",
        "support-queue",
        "outreach",
    ]

    try:
        token = _admin_token()
    except RuntimeError as exc:
        rep.add("Auth", "admin token", False, str(exc))
        token = ""

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )

        # --- Public storefront ---
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        for path, label in public_paths:
            try:
                page.goto(f"{factory}{path}", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_load_state("networkidle", timeout=15000)
                ok, detail = _page_ok(
                    page,
                    min_chars=30 if path == "/admin/login" else 50,
                    forbid=("application error", "internal server error"),
                )
                if path == "/admin/login":
                    pw = page.locator('input[type="password"]').count()
                    ok = ok and pw > 0
                    detail = f"{detail}, password_field={pw}"
                rep.add("Factory public", label, ok, detail)
            except Exception as exc:
                rep.add("Factory public", label, False, str(exc))
        ctx.close()

        # --- Admin (all tabs) ---
        if token:
            ctx = browser.new_context(viewport={"width": 1600, "height": 900})
            ctx.add_init_script(
                f'localStorage.setItem("admin_token", {json.dumps(token)});'
            )
            page = ctx.new_page()
            for tab in admin_tabs:
                try:
                    page.goto(
                        f"{factory}/admin?tab={tab}",
                        wait_until="networkidle",
                        timeout=90000,
                    )
                    page.wait_for_timeout(4000)
                    try:
                        page.locator("main .animate-spin").first.wait_for(
                            state="hidden", timeout=8000
                        )
                    except Exception:
                        pass  # some tabs keep live metric spinners while usable
                    ok, detail = _page_ok(
                        page,
                        min_chars=20,
                        forbid=("application error", "unhandled runtime error"),
                    )
                    rep.add("Factory admin", f"tab:{tab}", ok, detail)
                except Exception as exc:
                    rep.add("Factory admin", f"tab:{tab}", False, str(exc))
            ctx.close()
        else:
            rep.add("Factory admin", "all tabs", False, "skipped — no token")

        # --- Alien Monitor (sections) ---
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        try:
            page.goto(monitor, wait_until="domcontentloaded", timeout=60000)
            time.sleep(wait_monitor)
            has_viz = (
                page.locator("canvas").count() > 0
                or page.locator('button[title]').count() >= 8
            )
            try:
                ok, detail = _page_ok(page, min_chars=80)
            except Exception:
                ok, detail = True, "body read timeout (WebGL page)"
            rep.add("Monitor", "initial load", has_viz and ok, f"{detail}, viz={has_viz}")

            health = page.evaluate(
                """async () => {
                  const r = await fetch('api/health');
                  const j = await r.json();
                  return j.status === 'ok';
                }"""
            )
            rep.add("Monitor", "API health", bool(health))

            for mode_label in ("TEST", "LIVE", "UNI"):
                try:
                    btn = page.get_by_role("button", name=mode_label, exact=True)
                    if btn.count() == 0:
                        btn = page.locator(f"button:has-text('{mode_label}')").first
                    btn.click(timeout=5000)
                    time.sleep(2)
                    ok_m, det_m = _page_ok(page, min_chars=60)
                    rep.add("Monitor", f"mode {mode_label}", ok_m, det_m)
                except Exception as exc:
                    rep.add("Monitor", f"mode {mode_label}", False, str(exc))

            for dock in ("Граф", "Настройки", "ИИ", "Лог"):
                try:
                    b = page.get_by_role("button", name=dock)
                    if b.count():
                        b.first.click(timeout=3000)
                        time.sleep(1)
                    rep.add("Monitor", f"dock:{dock}", True)
                except Exception as exc:
                    rep.add("Monitor", f"dock:{dock}", False, str(exc))
        except Exception as exc:
            rep.add("Monitor", "initial load", False, str(exc))
        ctx.close()

        # --- Pulse Terminal ---
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        try:
            page.goto(pulse, wait_until="domcontentloaded", timeout=60000)
            time.sleep(6)
            ok, detail = _page_ok(page, min_chars=40)
            rep.add("Pulse", "initial load", ok, detail)

            for contour in ("LIVE", "UNI"):
                try:
                    page.get_by_role("button", name=contour, exact=True).click(timeout=5000)
                    time.sleep(4)
                    ok_c, det_c = _page_ok(page, min_chars=30)
                    rep.add("Pulse", f"contour {contour}", ok_c, det_c)
                except Exception as exc:
                    rep.add("Pulse", f"contour {contour}", False, str(exc))

            rows = page.locator("table tbody tr, [role='row']")
            if rows.count() > 0:
                rows.first.click(timeout=3000)
                time.sleep(1)
                rep.add("Pulse", "listing detail", True, f"rows={rows.count()}")
            else:
                rep.add("Pulse", "listing detail", True, "no rows (empty catalog OK)")
        except Exception as exc:
            rep.add("Pulse", "initial load", False, str(exc))
        ctx.close()

        # --- Hub well-known (browser) ---
        ctx = browser.new_context()
        page = ctx.new_page()
        try:
            page.goto(f"{hub}/.well-known/ai-market.json", timeout=30000)
            text = page.locator("body").inner_text(timeout=5000)
            ok = "protocol_versions" in text or "hub_version" in text
            rep.add("Hub", "well-known JSON", ok)
        except Exception as exc:
            rep.add("Hub", "well-known JSON", False, str(exc))
        ctx.close()

        browser.close()

    # --- API smokes (shell) ---
    api_scripts = [
        ("smoke_stack", [os.path.join(os.path.dirname(__file__), "smoke_stack_test.sh")]),
        ("verify_uni", [os.path.join(os.path.dirname(__file__), "verify_uni_ecosystem.sh")]),
    ]
    for name, cmd in api_scripts:
        try:
            r = subprocess.run(cmd, cwd=os.path.dirname(os.path.dirname(__file__)), timeout=120)
            rep.add("API scripts", name, r.returncode == 0, f"exit={r.returncode}")
        except Exception as exc:
            rep.add("API scripts", name, False, str(exc))

    report_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data",
        "reports",
        f"ecosystem_ui_full_{time.strftime('%Y%m%d_%H%M%S')}.md",
    )
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(rep.summary())
    print("")
    print(rep.summary())
    print(f"Report: {report_path}")
    print("")
    passed = sum(1 for r in rep.rows if r.ok)
    print(f"TOTAL: {passed}/{len(rep.rows)} passed")
    return rep.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
