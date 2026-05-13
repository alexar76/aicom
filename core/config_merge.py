"""
Layered YAML configuration merge
================================
Bundled defaults live under ``config/fragments/*.yaml`` (sorted by filename).
The primary file (``AIFACTORY_CONFIG_YAML``, legacy ``AIFACTORY_CONFIG``, or ``/app/config.yaml``)
is merged on top so Admin → Settings and deployment overrides win over repo defaults.

See ``docs/configuration.md``.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "config_yaml_path",
    "deep_merge",
    "load_merged_config",
]


def config_yaml_path() -> Path:
    """Resolved primary config path (overlay / persisted admin edits).

    Precedence: ``AIFACTORY_CONFIG_YAML`` → ``AIFACTORY_CONFIG`` (legacy) → ``/app/config.yaml``.
    """
    p = os.environ.get("AIFACTORY_CONFIG_YAML") or os.environ.get("AIFACTORY_CONFIG") or "/app/config.yaml"
    return Path(p)


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Return a new dict: ``base`` recursively updated with ``overlay`` (overlay wins)."""
    out = copy.deepcopy(base)
    for key, val in overlay.items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = deep_merge(out[key], val)
        else:
            out[key] = copy.deepcopy(val)
    return out


def load_merged_config(primary: str | Path | None = None) -> dict[str, Any]:
    """
    Load fragments from ``<parent>/config/fragments/*.yaml`` then overlay ``primary``.

    If the fragments directory is missing (e.g. minimal test fixtures), only ``primary`` is used.
    """
    primary_path = Path(primary) if primary is not None else config_yaml_path()
    merged: dict[str, Any] = {}
    frag_dir = primary_path.parent / "config" / "fragments"
    if frag_dir.is_dir():
        for fp in sorted(frag_dir.glob("*.yaml")):
            try:
                chunk = yaml.safe_load(fp.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError):
                chunk = {}
            if isinstance(chunk, dict):
                merged = deep_merge(merged, chunk)
    if primary_path.exists():
        try:
            overlay = yaml.safe_load(primary_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            overlay = None
        if isinstance(overlay, dict) and overlay:
            merged = deep_merge(merged, overlay)
    return merged
