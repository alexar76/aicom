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


def build_and_serve(slug: str, port: int, manifest) -> subprocess.Popen:
    app = DESKTOP / slug
    subprocess.run([str(FLUTTER), "pub", "get"], cwd=app, check=True)
    cmd = [
        str(FLUTTER),
        "build",
        "web",
        "--release",
        "--no-tree-shake-icons",
    ]
    if manifest.wallet:
        cmd += ["--dart-define=WALLET_KEY=" + DEV_WALLET_KEY]
    for key, value in manifest.dart_defines.items():
        cmd += [f"--dart-define={key}={value}"]
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
    page.get_by_role("button", name="New Pipeline").click(timeout=8000)
    page.wait_for_timeout(400)
    field = page.get_by_label("Pipeline name")
    field.fill("Demo Outreach Pipeline")
    page.get_by_role("button", name="Create").click(timeout=8000)
    page.wait_for_timeout(WAIT_MS)
    page.get_by_role("button", name="Export pipeline").click(timeout=8000)
    page.wait_for_timeout(WAIT_MS)


def _discovery_gap_detail(page) -> None:
    page.wait_for_timeout(3000)
    tiles = page.locator("flt-semantics").filter(has_text="Niche Score")
    if tiles.count() == 0:
        page.get_by_text("Refresh Telemetry", exact=False).first.click(timeout=8000)
        page.wait_for_timeout(4000)
    list_items = page.locator("[role='button']").filter(has_text="Score")
    if list_items.count() > 0:
        list_items.first.click(timeout=8000)
    else:
        page.locator("flt-semantics").filter(has_text="gaps found").first.click(timeout=8000)
    page.wait_for_timeout(WAIT_MS)


def _discovery_sdk_export(page) -> None:
    _discovery_gap_detail(page)
    page.get_by_role("button", name="Copy SDK Code").click(timeout=8000)
    page.wait_for_timeout(WAIT_MS)


def _freelance_review_report(page) -> None:
    _click_label(page, "Upload")
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
    page.get_by_role("button", name="Marketplace").click(timeout=8000)
    page.wait_for_timeout(WAIT_MS)


def _click_bottom_nav(page, index: int, *, slots: int = 4) -> None:
    vp = page.viewport_size or VIEWPORT
    w, h = vp["width"], vp["height"]
    x = int((index + 0.5) * w / slots)
    y = h - 40
    page.mouse.click(x, y)
    page.wait_for_timeout(WAIT_MS)


def _click_rail_nav(page, index: int) -> None:
    page.mouse.click(48, 100 + index * 80)
    page.wait_for_timeout(WAIT_MS)


def prepare_page(page, slug: str, url: str) -> None:
    page.goto(url, wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(WAIT_MS)


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
        _click_rail_nav(page, step.index)
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
    if action == "freelance_review_report":
        _freelance_review_report(page)
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

            for step in manifest.screens:
                prepare_page(page, slug, url)
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
