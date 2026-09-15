#!/usr/bin/env python3
"""Embed cartoon.json into cartoon.html and copy to ecosystem-landing."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARTOON_DIR = ROOT / "argus" / "docs" / "user-guide" / "humor"
TEMPLATE = CARTOON_DIR / "cartoon.html"
DATA = CARTOON_DIR / "cartoon.json"
LANDING = ROOT / "ecosystem-landing" / "argus" / "humor-cartoon.html"
MARKER = "/*__CARTOON_DATA__*/"


def main() -> None:
    html = TEMPLATE.read_text(encoding="utf-8")
    payload = DATA.read_text(encoding="utf-8").strip()
    if MARKER not in html:
        raise SystemExit(f"Marker {MARKER!r} not found in {TEMPLATE}")
    embedded = html.replace(MARKER, payload)
    LANDING.parent.mkdir(parents=True, exist_ok=True)
    LANDING.write_text(embedded, encoding="utf-8")
    print(f"wrote {LANDING.relative_to(ROOT)} (self-contained, {len(embedded):,} bytes)")


if __name__ == "__main__":
    main()
