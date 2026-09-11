#!/usr/bin/env python3
"""Manual trigger: same logic as post–DevOps auto-publish (see docs/auto-publish.md)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web.backend.services.auto_publish import try_publish_after_devops  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Publish data/code/<product_id>/ via configured provider.")
    ap.add_argument("product_id", help="e.g. prod-abc123def456")
    args = ap.parse_args()
    out = try_publish_after_devops(args.product_id.strip())
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") or out.get("skipped") else 1


if __name__ == "__main__":
    raise SystemExit(main())
