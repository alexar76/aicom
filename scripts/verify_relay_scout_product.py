#!/usr/bin/env python3
"""Verify Relay Scout product: pytest, methodology, backend runtime, demo quality."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web.backend.services.product_automated_verify import verify_product_automated


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--product-id", default="prod-relay-scout-6ce5e362")
    ap.add_argument("--json", action="store_true", help="Print full report as JSON")
    args = ap.parse_args()
    report = verify_product_automated(args.product_id.strip(), require_tests=True)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print("passed", report.get("passed"))
        tests = report.get("tests") or {}
        print("pytest", "skipped" if tests.get("skipped") else tests.get("passed"))
        meth = report.get("methodology") or {}
        print("methodology", meth.get("passed"), "score", meth.get("score"))
        backend = report.get("backend_runtime") or {}
        print("backend_runtime", backend.get("passed"))
        demo = report.get("demo") or {}
        print("demo score", demo.get("score"), "ok", report.get("demo_ok"))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
