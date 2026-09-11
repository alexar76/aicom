#!/usr/bin/env python3
"""Refresh QA/storefront telemetry from current code (automated gates, no LLM)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web.backend.services.product_storefront_refresh import refresh_product_storefront_telemetry


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--product-id", required=True)
    args = ap.parse_args()
    report = refresh_product_storefront_telemetry(args.product_id.strip())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
