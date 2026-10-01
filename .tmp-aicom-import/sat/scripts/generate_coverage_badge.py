#!/usr/bin/env python3
"""Write docs/badges/coverage.svg from coverage.json (pytest --cov-report=json)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IN = ROOT / "coverage.json"
DEFAULT_OUT = ROOT / "docs" / "badges" / "coverage.svg"


def _color(pct: float) -> str:
    if pct >= 80:
        return "#4c1"
    if pct >= 60:
        return "#97ca00"
    if pct >= 40:
        return "#dfb317"
    if pct >= 20:
        return "#fe7d37"
    return "#e05d44"


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
    argv = argv or sys.argv[1:]
    in_path = Path(argv[0]) if argv else DEFAULT_IN
    out_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_OUT
    if not in_path.is_file():
        print(f"coverage.json not found: {in_path}", file=sys.stderr)
        print(
            "Run: USE_SQLITE=true pytest -q --cov --cov-report=json:coverage.json",
            file=sys.stderr,
        )
        return 1
    data = json.loads(in_path.read_text(encoding="utf-8"))
    pct = float(data["totals"]["percent_covered"])
    value = f"{pct:.0f}%"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_svg("coverage", value, _color(pct)), encoding="utf-8")
    print(f"Wrote {out_path} ({value})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
