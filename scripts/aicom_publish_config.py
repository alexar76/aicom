#!/usr/bin/env python3
"""Load factory vs satellite paths from scripts/satellite-map.yaml."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

MAP_PATH = Path(__file__).resolve().parent / "satellite-map.yaml"

DEFAULT_RSYNC_EXCLUDES = [
    ".git",
    ".claude",
    ".cursor",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".dart_tool",
    "build",
    "dist",
    ".mesh_data",
    "data/state",
    "data/channels.db-shm",
    "data/channels.db-wal",
    "*.egg-info",
]


def _load_map() -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML required: pip install pyyaml")
    if not MAP_PATH.is_file():
        raise FileNotFoundError(MAP_PATH)
    return yaml.safe_load(MAP_PATH.read_text(encoding="utf-8")) or {}


def satellite_export_paths() -> list[str]:
    """Monorepo paths that belong in separate GitHub repos (not in factory)."""
    data = _load_map()
    paths: list[str] = []
    for sat in data.get("satellites") or []:
        if sat.get("id") == "aicom":
            continue
        for p in sat.get("paths") or []:
            if p == "plugins:plugins":
                paths.append("plugins")
            elif isinstance(p, str) and p.startswith("plugins:"):
                paths.append(p.split(":", 1)[1])
            elif p == ".":
                continue
            else:
                paths.append(str(p).rstrip("/"))
        for extra in (sat.get("export_layout") or {}).get("extra") or []:
            if isinstance(extra, dict) and extra.get("from"):
                paths.append(str(extra["from"]).rstrip("/"))
    seen: set[str] = set()
    out: list[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return sorted(out)


def factory_exclude_paths() -> list[str]:
    """Paths stripped from aicom factory remote."""
    data = _load_map()
    explicit: list[str] = []
    for sat in data.get("satellites") or []:
        if sat.get("id") == "aicom":
            explicit.extend(str(p).rstrip("/") for p in sat.get("exclude_paths") or [])
            break
    return sorted(dict.fromkeys([*explicit, *satellite_export_paths()]))


def rsync_exclude_args() -> list[str]:
    args: list[str] = []
    for p in DEFAULT_RSYNC_EXCLUDES:
        args.extend(["--exclude", p])
    for p in factory_exclude_paths():
        args.extend(["--exclude", f"{p}/"])
    return args


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list-excludes"
    if cmd == "list-excludes":
        for p in factory_exclude_paths():
            print(p)
        return 0
    if cmd == "rsync-args":
        for arg in rsync_exclude_args():
            print(arg)
        return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
