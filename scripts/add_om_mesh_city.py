#!/usr/bin/env python3
"""Deprecated: use scripts/add_gaia_atlas_sensor.py --kind open-meteo-pair.

Keeps working as a thin wrapper for mesh cities.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    argv = sys.argv[1:]
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "add_gaia_atlas_sensor.py"),
        "--kind",
        "open-meteo-pair",
        *argv,
    ]
    print(
        "NOTE: add_om_mesh_city.py → add_gaia_atlas_sensor.py --kind open-meteo-pair",
        file=sys.stderr,
    )
    print(
        "DISCLAIMER: only built-in kinds. See docs/add-gaia-atlas-sensor.md",
        file=sys.stderr,
    )
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
