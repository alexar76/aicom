#!/usr/bin/env python3
"""Write docs/badges/coverage.svg for smoke / validation repos (no pytest %)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "docs" / "badges" / "coverage.svg"


def _svg(label: str, value: str, fill: str = "#4c1") -> str:
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
    label = argv[0] if argv else "checks"
    value = argv[1] if len(argv) > 1 else "pass"
    out = Path(argv[2]) if len(argv) > 2 else DEFAULT_OUT
    fill = argv[3] if len(argv) > 3 else "#4c1"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_svg(label, value, fill), encoding="utf-8")
    print(f"Wrote {out} ({label}: {value})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
