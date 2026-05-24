#!/usr/bin/env python3
"""Capture multi-screen Playwright screenshots for desktop Flutter web SKUs."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "desktop-integrations"
FLUTTER = Path("/root/flutter/bin/flutter")
FIXTURES = ROOT / "scripts" / "fixtures"
SAMPLE_CONTRACT = FIXTURES / "sample-contract.txt"

sys.path.insert(0, str(ROOT / "scripts"))
from desktop_sku_manifest import DEV_WALLET_KEY, MANIFEST, ScreenStep, SkuManifest  # noqa: E402

VIEWPORT = {"width": 1440, "height": 900}
WAIT_MS = 1800


def _viewport(page) -> tuple[int, int]:
    vp = page.viewport_size or VIEWPORT
    return vp["width"], vp["height"]


def _enable_flutter_semantics(page) -> None:
    page.wait_for_timeout(900)
    for selector in ("flt-semantics-placeholder", '[aria-label="Enable accessibility"]'):
        loc = page.locator(selector)
        if loc.count() > 0:
            try:
                loc.first.click(timeout=3000)
                page.wait_for_timeout(500)
                return
            except Exception:
                continue
    page.keyboard.press("Tab")
    page.wait_for_timeout(250)
    page.keyboard.press("Enter")
    page.wait_for_timeout(500)


def build_and_serve(slug: str, port: int, manifest) -> subprocess.Popen:
    app = DESKTOP / slug
    subprocess.run([str(FLUTTER), "pub", "get"], cwd=app, check=True)
    cmd = [
        str(FLUTTER),
        "build",
        "web",
        "--release",
        "--no-tree-shake-icons",
        "--no-wasm-dry-run",
    ]
    if manifest.wallet:
        cmd += ["--dart-define=WALLET_KEY=" + DEV_WALLET_KEY]
    for key, value in manifest.dart_defines.items():
        cmd += [f"--dart-define={key}={value}"]
    try:
        subprocess.run(cmd, cwd=app, check=True)
    except subprocess.CalledProcessError:
        subprocess.run([str(FLUTTER), "clean"], cwd=app, check=True)
        subprocess.run(cmd, cwd=app, check=True)
    subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True)
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=app / "build" / "web",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(2)
    return proc


def _click_label(page, label: str) -> None:
    _enable_flutter_semantics(page)
    for locator in (
        page.get_by_role("button", name=label),
        page.get_by_role("tab", name=label),
        page.get_by_text(label, exact=True),
        page.get_by_text(label),
    ):
        try:
            locator.first.click(timeout=8000, force=True)
            page.wait_for_timeout(WAIT_MS)
            return
        except Exception:
            continue
    raise RuntimeError(f"nav label not found: {label}")


def _click_text(page, text: str) -> None:
    page.get_by_text(text, exact=True).first.click(timeout=12000)
    page.wait_for_timeout(WAIT_MS)


def _complete_interview_onboarding(page) -> None:
    if page.get_by_text("Today's Prep").count() > 0:
        return
    page.evaluate(
        """() => {
          localStorage.setItem('flutter.onboarding_complete', 'true');
        }"""
    )
    page.reload(wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(WAIT_MS)
    if page.get_by_text("Today's Prep").count() > 0:
        return
    _click_text(page, "Continue")
    _click_text(page, "Setup Wallet")
    _click_text(page, "Continue")
    page.get_by_placeholder("e.g. Google, Meta, Amazon").fill("Google")
    page.get_by_text("Google", exact=True).first.click(timeout=8000)
    page.get_by_placeholder("e.g. Software Engineer, Product Manager").fill("Software")
    page.get_by_text("Software Engineer", exact=True).first.click(timeout=8000)
    _click_text(page, "Start Preparing")


def _composer_export(page) -> None:
    _enable_flutter_semantics(page)
    w, h = _viewport(page)
    for locator in (
        page.get_by_role("button", name="New Pipeline"),
        page.get_by_text("New Pipeline", exact=True),
    ):
        try:
            locator.first.click(timeout=5000, force=True)
            break
        except Exception:
            continue
    else:
        page.mouse.click(w // 2, int(h * 0.58))
    page.wait_for_timeout(400)
    for locator in (
        page.get_by_label("Pipeline name"),
        page.get_by_placeholder("e.g., LinkedIn -> Email -> CRM"),
    ):
        try:
            locator.first.fill("Demo Outreach Pipeline", timeout=5000)
            break
        except Exception:
            continue
    else:
        page.keyboard.type("Demo Outreach Pipeline")
    for locator in (
        page.get_by_role("button", name="Create"),
        page.get_by_text("Create", exact=True),
    ):
        try:
            locator.first.click(timeout=5000, force=True)
            break
        except Exception:
            continue
    else:
        page.keyboard.press("Enter")
    page.wait_for_timeout(WAIT_MS)
    for locator in (
        page.get_by_role("button", name="Export pipeline"),
        page.locator('[aria-label="Export pipeline"]'),
    ):
        try:
            locator.first.click(timeout=5000, force=True)
            page.wait_for_timeout(WAIT_MS)
            return
        except Exception:
            continue
    page.mouse.click(w - 180, 36)
    page.wait_for_timeout(WAIT_MS)


def _discovery_gap_detail(page) -> None:
    _enable_flutter_semantics(page)
    page.wait_for_timeout(2500)
    for locator in (
        page.locator("[role='button']").filter(has_text="Score"),
        page.locator("flt-semantics").filter(has_text="Niche Score"),
    ):
        if locator.count() > 0:
            try:
                locator.first.click(timeout=5000, force=True)
                page.wait_for_timeout(WAIT_MS)
                return
            except Exception:
                continue
    page.mouse.click(210, 320)
    page.wait_for_timeout(WAIT_MS)


def _discovery_refresh(page) -> None:
    _enable_flutter_semantics(page)
    w, _ = _viewport(page)
    for locator in (
        page.get_by_text("Refresh Telemetry", exact=False),
        page.locator('[aria-label="Refresh Telemetry"]'),
        page.locator('[tooltip="Refresh Telemetry"]'),
    ):
        try:
            if locator.count() > 0:
                locator.first.click(timeout=5000, force=True)
                page.wait_for_timeout(WAIT_MS)
                return
        except Exception:
            continue
    page.mouse.click(w - 96, 36)
    page.wait_for_timeout(WAIT_MS)


def _discovery_sdk_export(page) -> None:
    _discovery_gap_detail(page)
    _enable_flutter_semantics(page)
    for locator in (
        page.get_by_role("button", name="Copy SDK Code"),
        page.get_by_text("Copy SDK Code", exact=True),
    ):
        try:
            locator.first.click(timeout=5000, force=True)
            page.wait_for_timeout(WAIT_MS)
            return
        except Exception:
            continue
    w, _ = _viewport(page)
    page.mouse.click(w - 150, 36)
    page.wait_for_timeout(WAIT_MS)


def _freelance_review_report(page) -> None:
    _click_bottom_nav(page, 1, slots=4)
    if not SAMPLE_CONTRACT.is_file():
        FIXTURES.mkdir(parents=True, exist_ok=True)
        SAMPLE_CONTRACT.write_text(
            "FREELANCE MASTER SERVICES AGREEMENT\n\n"
            "1. Payment terms: Net 30.\n"
            "2. IP assignment upon full payment.\n"
            "3. Non-compete for 12 months.\n",
            encoding="utf-8",
        )
    page.locator("input[type='file']").set_input_files(str(SAMPLE_CONTRACT))
    page.wait_for_timeout(8000)
    if page.get_by_text("Review:", exact=False).count() == 0:
        page.get_by_text("Choose File", exact=True).click(timeout=4000)
        page.wait_for_timeout(2000)
    page.wait_for_timeout(WAIT_MS)


def _wallet_popup(page) -> None:
    _enable_flutter_semantics(page)
    w, _ = _viewport(page)
    for locator in (
        page.get_by_role("button", name="Marketplace"),
        page.locator('[aria-label="Marketplace"]'),
    ):
        try:
            locator.first.click(timeout=5000, force=True)
            page.wait_for_timeout(WAIT_MS)
            return
        except Exception:
            continue
    page.mouse.click(w - 120, 36)
    page.wait_for_timeout(WAIT_MS)


def _wait_for_flutter_ready(page, slug: str) -> None:
    page.wait_for_selector("flt-glass-pane", state="attached", timeout=90000)
    page.wait_for_timeout(1200)
    markers = {
        "interview-prep-coach": ["AI Market", "Interview Prep Coach", "Today's Prep", "Discover Question Banks"],
        "personal-finance-coach": ["Financial Overview", "Finance Coach"],
        "capability-composer": ["No Pipeline Open", "Pipeline", "Capability Composer"],
        "cold-outreach-coach": ["Cold Outreach", "Outreach"],
        "creator-algorithm-coach": ["Creator", "Algorithm"],
        "discovery-prospector": ["Discovery", "Niche", "gaps"],
        "freelance-contract-reviewer": ["Contract", "Freelance"],
        "reputation-dashboard": ["Reputation", "Top", "Capabilities"],
    }
    for text in markers.get(slug, []):
        try:
            page.get_by_text(text, exact=False).first.wait_for(timeout=20000)
            page.wait_for_timeout(800)
            return
        except Exception:
            continue
    page.wait_for_timeout(2500)


def _click_bottom_nav(page, index: int, *, slots: int = 4) -> None:
    vp = page.viewport_size or VIEWPORT
    w, h = vp["width"], vp["height"]
    x = int((index + 0.5) * w / slots)
    y = h - 40
    page.mouse.click(x, y)
    page.wait_for_timeout(WAIT_MS)


def _click_rail_nav(page, index: int, *, label: str = "") -> None:
    _enable_flutter_semantics(page)
    if label:
        for locator in (
            page.locator("flt-semantics").filter(has_text=label),
            page.get_by_text(label, exact=True),
        ):
            try:
                if locator.count() > 0:
                    locator.first.click(timeout=6000, force=True)
                    page.wait_for_timeout(WAIT_MS)
                    return
            except Exception:
                continue
    page.mouse.click(40, 84 + index * 72)
    page.wait_for_timeout(WAIT_MS)


def _interview_mock_interview(page) -> None:
    _click_bottom_nav(page, 0, slots=4)
    page.get_by_text("Mock Interview", exact=False).first.click(timeout=8000)
    page.wait_for_timeout(WAIT_MS)


def prepare_page(page, slug: str, url: str, *, fragment: str = "") -> None:
    if slug == "interview-prep-coach":
        page.add_init_script(
            """() => {
              localStorage.setItem('flutter.onboarding_complete', 'true');
            }"""
        )
    target = f"{url}?tab={fragment}" if fragment else url
    page.goto(target, wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(WAIT_MS)
    _enable_flutter_semantics(page)
    _wait_for_flutter_ready(page, slug)
    tab_markers = {
        "import": "Import bank CSVs",
        "marketplace": "Finance Marketplace",
        "privacy": "never leaves this device",
        "discover": "Discover Capabilities",
        "templates": "Pipeline Templates",
    }
    marker = tab_markers.get(fragment)
    if marker:
        try:
            page.get_by_text(marker, exact=False).first.wait_for(timeout=15000)
            page.wait_for_timeout(600)
        except Exception:
            page.wait_for_timeout(2000)


def run_step(page, step: ScreenStep, manifest: SkuManifest) -> None:
    action = step.action
    if action in ("landing", "interview_onboarding"):
        return
    if action == "nav_label":
        _click_label(page, step.label)
        return
    if action == "nav_bottom":
        _click_bottom_nav(page, step.index, slots=manifest.bottom_nav_slots)
        return
    if action == "nav_rail":
        _click_rail_nav(page, step.index, label=step.label)
        return
    if action == "click_text":
        page.get_by_text(step.label, exact=False).first.click(timeout=8000)
        page.wait_for_timeout(WAIT_MS)
        return
    if action == "composer_export":
        _composer_export(page)
        return
    if action == "discovery_gap_detail":
        _discovery_gap_detail(page)
        return
    if action == "discovery_sdk_export":
        _discovery_sdk_export(page)
        return
    if action == "discovery_refresh":
        _discovery_refresh(page)
        return
    if action == "freelance_review_report":
        _freelance_review_report(page)
        return
    if action == "interview_mock":
        _interview_mock_interview(page)
        return
    if action == "wallet_popup":
        _wallet_popup(page)
        return
    raise ValueError(f"unknown action: {action}")


def capture_slug(slug: str) -> None:
    from playwright.sync_api import sync_playwright

    manifest = MANIFEST[slug]
    port = manifest.port
    shots_dir = DESKTOP / slug / "assets" / "screenshots"
    shots_dir.mkdir(parents=True, exist_ok=True)

    print(f"==> {slug} ({len(manifest.screens)} screens)")
    proc = build_and_serve(slug, port, manifest)
    url = f"http://127.0.0.1:{port}/"
    dash_names = {
        "dashboard",
        "overview",
        "canvas",
        "gaps-list",
        "prep-dashboard",
        "top-capabilities",
    }
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport=VIEWPORT)

            for i, step in enumerate(manifest.screens):
                fragment = step.fragment or ""
                if i == 0 or fragment or step.action in ("landing", "interview_onboarding"):
                    prepare_page(page, slug, url, fragment=fragment)
                if step.action not in ("landing", "interview_onboarding"):
                    run_step(page, step, manifest)
                out = shots_dir / f"{step.name}.png"
                page.screenshot(path=str(out), full_page=False)
                print(f"    saved {out.name}")
                if step.name in dash_names:
                    (shots_dir / "dashboard.png").write_bytes(out.read_bytes())

            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def main() -> None:
    targets = sys.argv[1:] if len(sys.argv) > 1 else list(MANIFEST.keys())
    failed: list[str] = []
    for slug in targets:
        if slug not in MANIFEST:
            print(f"unknown slug: {slug}", file=sys.stderr)
            sys.exit(1)
        try:
            capture_slug(slug)
        except Exception as exc:
            print(f"FAILED {slug}: {exc}", file=sys.stderr)
            failed.append(slug)
    if failed:
        print(f"Capture incomplete: {', '.join(failed)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
