#!/usr/bin/env python3
"""Set general.auto_pipeline in config.yaml (Docker: /app/config.yaml)."""
from __future__ import annotations

import os
import sys

import yaml


def main() -> None:
    config_path = os.environ.get("AIFACTORY_CONFIG", "/app/config.yaml")
    raw = os.environ.get("AUTO_PIPELINE_VALUE", "true").strip().lower()
    enabled = raw in ("1", "true", "yes", "on")

    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data.setdefault("general", {})["auto_pipeline"] = enabled
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
    print(f"[set_auto_pipeline] general.auto_pipeline = {enabled}", file=sys.stderr)


if __name__ == "__main__":
    main()
