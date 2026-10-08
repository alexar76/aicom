#!/usr/bin/env python3
"""Write the satellite map a public repo may carry: the central map minus every
`github_published: false` entry (their descriptions, paths and exclude_paths included).

    python3 scripts/write_published_satellite_map.py <dest-file>

The alien-monitor satellite reads its map at runtime, so its mirror ships one — this one,
never the raw scripts/satellite-map.yaml.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sync_knowledge_base import satellite_map_mirror_text  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    raw = (ROOT / "scripts" / "satellite-map.yaml").read_text(encoding="utf-8")
    dest = Path(argv[0])
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(satellite_map_mirror_text("scripts/satellite-map.yaml", raw), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
