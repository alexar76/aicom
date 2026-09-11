#!/usr/bin/env python3
"""Run realistic demo gates + headless browser E2E on a product (for CI / manual smoke)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Docker / monorepo: application root is /app
_ROOT = os.environ.get("AICOM_APP_ROOT", "/app")
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Real Chromium pass — override via env if needed
os.environ.setdefault("AIFACTORY_BROWSER_E2E", "1")
os.environ.setdefault("AIFACTORY_BROWSER_UI_CLICKS", "8")
os.environ.setdefault("AIFACTORY_STRICT_DEMO_GATES", "1")

PID = sys.argv[1] if len(sys.argv) > 1 else "prod-953eac2586f9"
ROOT = "/app/data"


def main() -> int:
    from web.backend.services.demo_quality import assess_product_demo, quality_gates_pass
    from web.backend.services.browser_preview_e2e import run_browser_preview_e2e

    spec_inner: dict = {}
    sp = Path(f"{ROOT}/specs/{PID}/specification.json")
    if sp.is_file():
        raw = json.loads(sp.read_text(encoding="utf-8"))
        spec_inner = raw.get("specification") or {}

    demo = assess_product_demo(PID, spec_inner, data_root=ROOT)
    print("=== STATIC DEMO QUALITY ===")
    print(json.dumps({k: demo.get(k) for k in ("score", "grade", "issues", "spec_coverage_pct")}, indent=2))
    print("quality_gates_pass:", quality_gates_pass(demo))

    print("\n=== HEADLESS CHROMIUM + UI CLICKS ===")
    be = run_browser_preview_e2e(PID, ROOT)
    slim = {
        k: be.get(k)
        for k in (
            "passed",
            "skipped",
            "url",
            "visible_text_length",
            "has_visible_structure",
            "issues",
            "visual_render_audit",
        )
        if k in be
    }
    ui = be.get("ui_interaction") or {}
    slim["ui_interaction"] = {
        "skipped": ui.get("skipped"),
        "clicks_attempted": ui.get("clicks_attempted"),
        "click_log_preview": (ui.get("click_log") or [])[:6],
        "ui_issues": (ui.get("issues") or [])[:8],
    }
    print(json.dumps(slim, indent=2, ensure_ascii=False))

    ok_static = quality_gates_pass(demo)
    ok_browser = bool(be.get("skipped")) or bool(be.get("passed"))
    print("\n=== RESULT ===")
    print(f"static_gates_ok={ok_static}  browser_e2e_ok={ok_browser}")
    if ok_static and ok_browser:
        print("REALISTIC COMBINED BAR: PASS")
        return 0
    print("REALISTIC COMBINED BAR: FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
