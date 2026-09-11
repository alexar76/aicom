#!/usr/bin/env python3
"""
Best-effort demo data seed for a **generated** full_software product.

Looks for (in order):
  1. ``data/code/<product_id>/scripts/seed_factory_demo.py`` — run with Python if present.
  2. ``data/code/<product_id>/backend/scripts/seed_factory_demo.py``
  3. ``make seed-demo`` / ``npm run seed`` — not invoked automatically (too stack-specific).

If nothing is found, prints guidance — the Developer should ship **implementation_contract** demo seed
per Architect (seeded users, tasks for charts, etc.).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--product-id", required=True)
    ap.add_argument(
        "--data-root",
        default="/app/data",
        help="Factory data root (default /app/data in container, ./data on host bind-mount)",
    )
    args = ap.parse_args()

    root = Path(args.data_root)
    cid = args.product_id.strip()
    code = root / "code" / cid

    candidates = [
        code / "scripts" / "seed_factory_demo.py",
        code / "backend" / "scripts" / "seed_factory_demo.py",
        code / "seed_factory_demo.py",
    ]

    for script in candidates:
        if script.is_file():
            print(f"[seed] Running {script}")
            r = subprocess.run([sys.executable, str(script)], cwd=str(code))
            return int(r.returncode)

    print(
        "[seed] No seed_factory_demo.py found — generated repo should expose seed per Architect "
        "(demo users + tasks + chart data). Optional endpoint POST /api/demo/seed for sandbox.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
