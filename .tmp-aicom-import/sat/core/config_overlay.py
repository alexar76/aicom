"""Primary config overlay bootstrap and legacy JSON mirror under ``data/state/``."""

from __future__ import annotations

import json
import logging
from typing import Any

import yaml

from core.config_merge import load_merged_config
from core.paths import config_path, state_dir

logger = logging.getLogger(__name__)


def _legacy_state_config_json_path():
    return state_dir() / "config.json"


def sync_state_config_json_mirror(*, merged: dict[str, Any] | None = None) -> None:
    """Write merged platform config to ``data/state/config.json`` for operator scripts."""
    if merged is None:
        merged = load_merged_config(config_path())
    dest = _legacy_state_config_json_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def ensure_primary_config_overlay() -> None:
    """Ensure the YAML overlay exists and the legacy JSON mirror is up to date."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_text("general: {}\n", encoding="utf-8")
        logger.info("Created empty config overlay at %s", path)
    try:
        sync_state_config_json_mirror()
    except Exception as exc:
        logger.warning("Could not sync legacy state config JSON mirror: %s", exc)


def patch_primary_overlay(updates: dict[str, Any]) -> None:
    """Merge flat dot-notation keys into the primary YAML overlay and refresh JSON mirror."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, yaml.YAMLError) as exc:
            logger.warning("Could not read config overlay %s: %s", path, exc)

    for key, value in updates.items():
        parts = key.split(".")
        target = data
        for part in parts[:-1]:
            child = target.get(part)
            if not isinstance(child, dict):
                child = {}
                target[part] = child
            target = child
        target[parts[-1]] = value

    path.write_text(
        yaml.dump(data, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    sync_state_config_json_mirror()
