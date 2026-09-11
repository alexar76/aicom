#!/usr/bin/env python3
"""Entrypoint helper: create config overlay + legacy state/config.json mirror."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config_overlay import ensure_primary_config_overlay


def main() -> int:
    ensure_primary_config_overlay()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
