#!/usr/bin/env python3
"""Where a file in a published satellite lives in the monorepo.

``mirror_satellites.sh`` does not always copy one monorepo folder to the root of a
satellite. The desktop repo builds ``apps/<sku>`` from ``desktop-integrations/<sku>``,
the plugins repo folds ``aimarket-hub/plugins/aimarket-provenance`` into
``plugins/``, attested-memory carries three apps beside its hub, and several oracle
satellites vendor ``oracles/core`` as ``vendor/oracle-core``. A merged pull request
that touches one of those files has to land at the monorepo path it came from, not
under the satellite's root folder.

``import_satellite_pr.sh`` asks this module for the satellite's map:

    python3 scripts/satellite_import_paths.py <satellite-id>

prints one header line ``<repo>|<mode>`` and then one line per mapping,
``<satellite prefix>|<monorepo prefix>``, most specific prefix first. An empty
satellite prefix is the repository root. The separator is ``|`` and not a tab:
``read`` collapses a leading tab, which would lose the empty root prefix.
"""

from __future__ import annotations

import posixpath
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "scripts" / "satellite-map.yaml"

# Satellites that ship oracles/core vendored (mirror_satellites.sh, the oracle family).
VENDORED_ORACLE_CORE = ("vendor/oracle-core", "oracles/core")


def load_satellite(sat_id: str, map_path: Path = MAP_PATH) -> dict[str, Any] | None:
    data = yaml.safe_load(map_path.read_text(encoding="utf-8")) or {}
    for entry in data.get("satellites") or []:
        if entry.get("id") == sat_id:
            return entry
    return None


def history_mode(entry: dict[str, Any]) -> str:
    """``live`` unless the entry opts out with ``history: mirror``."""
    return "mirror" if str(entry.get("history", "live")).strip().lower() == "mirror" else "live"


def _clean(path: str) -> str:
    path = posixpath.normpath(path.strip().strip("/")) if path.strip().strip("/") else ""
    return "" if path == "." else path


def _root_from_paths(paths: list[str]) -> str:
    """A satellite without an export layout publishes its first path at the root.

    A file path (the profile README) publishes its folder."""
    if not paths:
        return ""
    first = paths[0].split(":", 1)[0]
    clean = _clean(first)
    if first.endswith("/") or not posixpath.splitext(clean)[1]:
        return clean
    return posixpath.dirname(clean)


def import_path_map(entry: dict[str, Any]) -> list[tuple[str, str]]:
    """(satellite prefix, monorepo prefix) pairs, longest satellite prefix first."""
    layout = entry.get("export_layout") or {}
    paths = [str(p) for p in entry.get("paths") or []]
    pairs: dict[str, str] = {}

    root = layout.get("root_from") or layout.get("monorepo_from")
    if root:
        pairs[""] = _clean(str(root))
    elif layout.get("apps_from"):
        pairs[""] = _clean(str(layout["apps_from"]))
    else:
        pairs[""] = _root_from_paths(paths)

    if layout.get("apps_from"):
        pairs["apps"] = _clean(str(layout["apps_from"]))
    if layout.get("packages_from"):
        pairs["packages"] = _clean(str(layout["packages_from"]))
    if layout.get("plugins_from"):
        pairs["plugins"] = _clean(str(layout["plugins_from"]))
    for extra in layout.get("extra") or []:
        if extra.get("from") and extra.get("to"):
            pairs[_clean(str(extra["to"]))] = _clean(str(extra["from"]))
    # "src:dst" in paths: monorepo src published at satellite dst.
    for raw in paths:
        if ":" in raw:
            src, dst = raw.split(":", 1)
            pairs.setdefault(_clean(dst), _clean(src))

    vendored, canonical = VENDORED_ORACLE_CORE
    root_dir = pairs[""]
    if not (ROOT / root_dir / vendored).exists():
        pairs.setdefault(vendored, canonical)

    return sorted(pairs.items(), key=lambda kv: (-len(kv[0]), kv[0]))


def map_path(repo_path: str, mapping: list[tuple[str, str]]) -> str:
    """The monorepo path of one satellite path."""
    clean = _clean(repo_path)
    for prefix, target in mapping:
        if not prefix:
            return posixpath.join(target, clean) if target else clean
        if clean == prefix or clean.startswith(prefix + "/"):
            rest = clean[len(prefix):].lstrip("/")
            return posixpath.join(target, rest) if rest else target
    return clean


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: satellite_import_paths.py <satellite-id>", file=sys.stderr)
        return 2
    entry = load_satellite(argv[1])
    if entry is None:
        return 1
    print(f"{entry.get('repo') or argv[1]}|{history_mode(entry)}")
    for prefix, target in import_path_map(entry):
        print(f"{prefix}|{target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
