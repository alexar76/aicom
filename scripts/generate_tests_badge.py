#!/usr/bin/env python3
"""Generate tests badge artifacts from the real pytest count.

Writes:
  * ``docs/badges/tests.json`` — shields endpoint payload (optional / legacy)
  * ``docs/badges/tests.svg`` — self-hosted SVG (preferred in READMEs; no shields.io)

Usage:
  python scripts/generate_tests_badge.py --rootdir skopos --out skopos/docs/badges/tests.json
  python scripts/generate_tests_badge.py --count 227 --out docs/badges/tests.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def _collect_count(rootdir: Path) -> int:
    """Return the number of collected tests via ``pytest --collect-only -q``."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=str(rootdir),
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    m = re.search(r"(\d+)\s+tests?\s+collected", out)
    if m:
        return int(m.group(1))
    count = sum(1 for line in out.splitlines() if "::" in line)
    if count:
        return count
    raise RuntimeError(f"could not determine test count:\n{out[-2000:]}")


def _color_shields(count: int) -> str:
    return "brightgreen" if count > 0 else "lightgrey"


def _color_hex(count: int) -> str:
    return "#4c1" if count > 0 else "#9f9f9f"


def build_payload(count: int) -> dict:
    return {
        "schemaVersion": 1,
        "label": "tests",
        "message": f"{count} passing",
        "color": _color_shields(count),
    }


def _svg(label: str, value: str, fill: str) -> str:
    lw = len(label) * 6.5 + 10
    vw = len(value) * 6.5 + 10
    tw = lw + vw
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{tw:.0f}" height="20" role="img" aria-label="{label}: {value}">
  <title>{label}: {value}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r"><rect width="{tw:.0f}" height="20" rx="3" fill="#fff"/></clipPath>
  <g clip-path="url(#r)">
    <rect width="{lw:.0f}" height="20" fill="#555"/>
    <rect x="{lw:.0f}" width="{vw:.0f}" height="20" fill="{fill}"/>
    <rect width="{tw:.0f}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
    <text x="{lw/2:.1f}" y="14" fill="#010101" fill-opacity=".3">{label}</text>
    <text x="{lw/2:.1f}" y="13">{label}</text>
    <text x="{lw + vw/2:.1f}" y="14" fill="#010101" fill-opacity=".3">{value}</text>
    <text x="{lw + vw/2:.1f}" y="13">{value}</text>
  </g>
</svg>
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", type=int, help="explicit test count (skip collection)")
    ap.add_argument("--rootdir", type=Path, help="repo dir to collect tests from")
    ap.add_argument("--out", type=Path, required=True, help="output JSON path")
    ap.add_argument(
        "--svg",
        type=Path,
        help="optional SVG path (default: sibling tests.svg next to --out)",
    )
    args = ap.parse_args(argv)

    if args.count is not None:
        count = args.count
    elif args.rootdir is not None:
        count = _collect_count(args.rootdir)
    else:
        count = _collect_count(Path.cwd())

    payload = build_payload(count)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    svg_path = args.svg or args.out.with_name("tests.svg")
    value = payload["message"]
    svg_path.write_text(_svg("tests", value, _color_hex(count)), encoding="utf-8")
    print(f"Wrote {args.out} + {svg_path} → {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
