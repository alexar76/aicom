#!/usr/bin/env python3
"""
Deploy-quality finalize for Relay Scout: verify automated gates, then COMPLETED.

Stops dev↔QA ping-pong when manual fix already meets bar for reasonable quality.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--product-id", default="prod-relay-scout-6ce5e362")
    ap.add_argument("--skip-verify", action="store_true")
    ap.add_argument("--force", action="store_true", help="Complete even if verify fails (not recommended)")
    args = ap.parse_args()
    pid = args.product_id.strip()

    if not args.skip_verify:
        verify = subprocess.run(
            [sys.executable, str(ROOT / "scripts/verify_relay_scout_product.py"), "--product-id", pid],
            cwd=str(ROOT),
        )
        if verify.returncode != 0 and not args.force:
            print("Verify failed — not completing product (use --force to override)", file=sys.stderr)
            return verify.returncode

    # Patch spec + methodology telemetry before completion
    resume = subprocess.run(
        [sys.executable, str(ROOT / "scripts/resume_relay_scout_after_fix.py"), "--product-id", pid, "--no-qa"],
        cwd=str(ROOT),
    )
    if resume.returncode != 0:
        return resume.returncode

    complete = subprocess.run(
        [sys.executable, str(ROOT / "scripts/operator_complete_product.py"), "--product-id", pid, "--force", "--no-pause"],
        cwd=str(ROOT),
    )
    return complete.returncode


if __name__ == "__main__":
    raise SystemExit(main())
