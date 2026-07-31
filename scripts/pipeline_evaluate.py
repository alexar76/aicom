#!/usr/bin/env python3
"""
Evaluate a product against factory criteria: spec quality gate + demo/sandbox heuristics.

Usage (in container, from /app):
  python3 scripts/pipeline_evaluate.py prod-xxxxxxxxxxxx
  AIFACTORY_DATA_ROOT=./data python3 scripts/pipeline_evaluate.py prod-xxx  # repo host
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Spec gate + demo quality scorecard for a product_id")
    parser.add_argument("product_id", help="e.g. prod-abc123def456")
    args = parser.parse_args()
    pid = args.product_id.strip()
    data_root = Path(os.environ.get("AIFACTORY_DATA_ROOT", "/app/data"))

    from agents.product_profile import FULL_SOFTWARE, normalize_delivery_profile
    from agents.spec_quality_gate import validate_specification
    from web.backend.services.demo_quality import assess_product_demo, quality_gates_pass

    spec_path = data_root / "specs" / pid / "specification.json"
    if not spec_path.is_file():
        print(f"ERROR: no specification at {spec_path}")
        return 2

    wrapper = json.loads(spec_path.read_text(encoding="utf-8"))
    spec = wrapper.get("specification") if isinstance(wrapper.get("specification"), dict) else wrapper
    raw_prof = spec.get("delivery_profile") if isinstance(spec, dict) else None
    profile = normalize_delivery_profile(str(raw_prof)) if raw_prof else FULL_SOFTWARE

    print(f"=== Product {pid} ===")
    print(f"delivery_profile: {profile}")

    ok, issues = validate_specification(spec if isinstance(spec, dict) else {}, profile)
    print("\n--- Spec quality gate ---")
    print("PASS" if ok else "FAIL")
    if issues:
        for i in issues:
            print(f"  - {i}")

    demo = assess_product_demo(pid, spec if isinstance(spec, dict) else None, data_root=str(data_root))
    gates = quality_gates_pass(demo)
    print("\n--- Demo / sandbox heuristics ---")
    print(f"score: {demo.get('score')}  grade: {demo.get('grade')}  sandbox_ready: {demo.get('sandbox_ready')}")
    print(f"quality_gates_pass: {gates}")
    if demo.get("spec_coverage_pct") is not None:
        print(f"spec_coverage_pct (keyword): {demo.get('spec_coverage_pct')}")
    for iss in demo.get("issues") or []:
        if isinstance(iss, dict):
            print(f"  [{iss.get('code')}] {iss.get('detail')}")

    print("\n=== Overall (ship bar) ===")
    if ok and gates:
        print("PASS — spec structure OK and demo gates OK")
        return 0
    print("FAIL — fix spec and/or demo before treating as shippable")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
