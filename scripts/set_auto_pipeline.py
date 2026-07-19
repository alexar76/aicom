#!/usr/bin/env python3
"""Set ``general.auto_pipeline`` on the primary config overlay (not full merged dump).

Reads and writes only the primary file from :func:`core.paths.config_path` (respects
``AIFACTORY_CONFIG_PATH``, ``AIFACTORY_CONFIG_YAML``, legacy ``AIFACTORY_CONFIG``).

See ``docs/configuration.md``.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.paths import config_path as primary_config_path


def main() -> None:
    path = primary_config_path()
    raw = os.environ.get("AUTO_PIPELINE_VALUE", "true").strip().lower()
    enabled = raw in ("1", "true", "yes", "on")

    data: dict = {}
    if path.is_file():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            data = {}
    if not isinstance(data, dict):
        data = {}
    gen = data.get("general")
    if not isinstance(gen, dict):
        gen = {}
    gen["auto_pipeline"] = enabled
    data["general"] = gen
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(data, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(f"[set_auto_pipeline] general.auto_pipeline = {enabled}", file=sys.stderr)


if __name__ == "__main__":
    main()
